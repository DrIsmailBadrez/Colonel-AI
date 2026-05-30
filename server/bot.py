"""Colonel AI — Voice bot pipeline (Pipecat + Nemotron + Gradium).

Run locally:  uv run bot.py
"""

import asyncio
import os

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import (
    RunnerArguments,
    SmallWebRTCRunnerArguments,
    WebSocketRunnerArguments,
)
from pipecat.runner.utils import parse_telephony_websocket
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.gradium.tts import GradiumTTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.turns.user_turn_strategies import FilterIncompleteUserTurnStrategies
from pipecat.workers.runner import WorkerRunner

from nemotron_llm import VLLMOpenAILLMService
from nvidia_stt import NVidiaWebSocketSTTService
from prompts import build_system_prompt
from transcript_logger import TranscriptLogger
from tools import (
    dispatch_unit,
    end_call,
    move_unit,
    query_area,
    report_contact,
    report_status,
    set_caller_context,
)

load_dotenv(override=True)

STATE_URL = os.getenv("STATE_SERVER_URL", "http://localhost:8000")


async def fetch_state_and_caller(soldier_id: str | None) -> tuple[dict, dict | None]:
    """Fetch the battlefield state and caller's WarItem from the state server."""
    caller_item = None
    state = {"items": {}, "events": []}
    try:
        async with aiohttp.ClientSession() as session:
            if soldier_id:
                async with session.get(f"{STATE_URL}/api/item/{soldier_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if "error" not in data:
                            caller_item = data

            async with session.get(f"{STATE_URL}/api/state") as resp:
                if resp.status == 200:
                    state = await resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch state from {STATE_URL}: {e}")

    return state, caller_item


async def run_bot(
    transport: BaseTransport,
    soldier_id: str | None = None,
    audio_in_sample_rate: int = 16000,
    audio_out_sample_rate: int = 24000,
):
    """Main bot logic.

    Args:
        transport: The transport to use.
        soldier_id: ID of the calling soldier (from UI click-to-call).
        audio_in_sample_rate: Input audio sample rate in Hz.
        audio_out_sample_rate: Output audio sample rate in Hz.
    """
    logger.info(f"Starting Colonel AI bot — soldier_id={soldier_id}")

    # Fetch battlefield state and caller identity
    state, caller_item = await fetch_state_and_caller(soldier_id)
    set_caller_context(soldier_id, caller_item)

    # Build system prompt with battlefield context
    system_instruction = build_system_prompt(state, caller_item)

    # --- Tool functions ---
    tool_functions = [
        report_contact,
        query_area,
        move_unit,
        dispatch_unit,
        report_status,
        end_call,
    ]
    tools = ToolsSchema(standard_tools=tool_functions)

    # --- STT ---
    stt = NVidiaWebSocketSTTService(
        url=os.environ["NVIDIA_ASR_URL"],
        strip_interim_prefix=True,
    )

    # --- LLM ---
    enable_thinking = os.getenv("NEMOTRON_ENABLE_THINKING", "false").lower() == "true"
    llm = VLLMOpenAILLMService(
        api_key=os.getenv("NEMOTRON_LLM_API_KEY", "EMPTY"),
        base_url=os.environ["NEMOTRON_LLM_URL"],
        settings=VLLMOpenAILLMService.Settings(
            model=os.getenv("NEMOTRON_LLM_MODEL", "nvidia/nemotron-3-super"),
            system_instruction=system_instruction,
            extra={"extra_body": {"chat_template_kwargs": {"enable_thinking": enable_thinking}}},
        ),
    )

    # --- TTS ---
    tts = GradiumTTSService(
        api_key=os.environ["GRADIUM_API_KEY"],
        settings=GradiumTTSService.Settings(
            voice=os.getenv("GRADIUM_VOICE_ID", "_6Aslh2DxfmnRLmP"),
        ),
    )

    # Register tools on LLM
    for fn in tool_functions:
        llm.register_direct_function(fn)

    # --- Transcript Loggers ---
    # Two instances: one captures user speech (before aggregator consumes it),
    # one captures bot speech (after LLM emits it). Each naturally only sees
    # the frame types available at its pipeline position.
    sid = soldier_id or "UNKNOWN"
    user_transcript_logger = TranscriptLogger(soldier_id=sid, state_url=STATE_URL)
    bot_transcript_logger = TranscriptLogger(soldier_id=sid, state_url=STATE_URL)

    context = LLMContext(tools=tools)
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
            user_turn_strategies=FilterIncompleteUserTurnStrategies(),
        ),
    )

    # Pipeline:
    #   user_transcript_logger before aggregator → captures TranscriptionFrame (user speech)
    #   bot_transcript_logger after LLM → captures TextFrame between LLMFullResponseStart/End
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_transcript_logger,
            user_aggregator,
            llm,
            bot_transcript_logger,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            audio_in_sample_rate=audio_in_sample_rate,
            audio_out_sample_rate=audio_out_sample_rate,
        ),
    )

    # --- Background state refresh ---
    # The simulation engine moves units every 1s. Without periodic refresh the
    # LLM only sees state from the last tool call, so it gives stale answers.
    refresh_task: asyncio.Task | None = None

    async def _periodic_state_refresh():
        """Fetch fresh state every 1s and update the LLM system instruction."""
        while True:
            await asyncio.sleep(1.0)
            try:
                fresh_state, fresh_caller = await fetch_state_and_caller(soldier_id)
                set_caller_context(soldier_id, fresh_caller)
                llm._settings.system_instruction = build_system_prompt(
                    fresh_state, fresh_caller
                )
            except Exception as e:
                logger.debug(f"Periodic state refresh failed: {e}")

    # Determine greeting callsign
    greeting = "Go ahead" + (f" {caller_item['callsign']}" if caller_item else ", soldier")

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        nonlocal refresh_task
        logger.info("Client connected")
        # Start periodic state refresh
        refresh_task = asyncio.create_task(_periodic_state_refresh())
        context.add_message(
            {
                "role": "user",
                "content": f"A soldier just called in on the radio. Greet them: '{greeting}.'",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        nonlocal refresh_task
        logger.info("Client disconnected")
        if refresh_task:
            refresh_task.cancel()
            refresh_task = None
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point — called by Pipecat runner."""

    soldier_id: str | None = None
    transport_overrides: dict = {}

    # Krisp noise filter in cloud deployments
    if os.environ.get("ENV") != "local":
        from pipecat.audio.filters.krisp_viva_filter import KrispVivaFilter

        krisp_filter = KrispVivaFilter()
    else:
        krisp_filter = None

    match runner_args:
        case SmallWebRTCRunnerArguments():
            webrtc_connection: SmallWebRTCConnection = runner_args.webrtc_connection

            # Extract soldier_id from requestData (sent by UI click-to-call)
            body = runner_args.body or {}
            soldier_id = body.get("soldier_id")
            logger.info(f"SmallWebRTC connection — soldier_id={soldier_id}")

            transport = SmallWebRTCTransport(
                webrtc_connection=webrtc_connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_in_filter=krisp_filter,
                    audio_out_enabled=True,
                ),
            )

        case WebSocketRunnerArguments():
            # Twilio media streams: 8 kHz u-law
            transport_overrides["audio_in_sample_rate"] = 8000
            transport_overrides["audio_out_sample_rate"] = 8000

            _, call_data = await parse_telephony_websocket(runner_args.websocket)

            # Could extract soldier_id from Twilio custom params in the future
            serializer = TwilioFrameSerializer(
                stream_sid=call_data["stream_id"],
                call_sid=call_data["call_id"],
                account_sid=os.environ["TWILIO_ACCOUNT_SID"],
                auth_token=os.environ["TWILIO_AUTH_TOKEN"],
            )

            transport = FastAPIWebsocketTransport(
                websocket=runner_args.websocket,
                params=FastAPIWebsocketParams(
                    audio_in_enabled=True,
                    audio_in_filter=krisp_filter,
                    audio_out_enabled=True,
                    add_wav_header=False,
                    serializer=serializer,
                ),
            )

        case _:
            logger.error(f"Unsupported runner arguments type: {type(runner_args)}")
            return

    await run_bot(transport, soldier_id=soldier_id, **transport_overrides)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
