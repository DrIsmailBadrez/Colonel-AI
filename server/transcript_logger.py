"""Pipeline processor that captures user and bot speech, POSTs to state server."""

import aiohttp
from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TranscriptLogger(FrameProcessor):
    """Sits in the pipeline and captures user transcriptions + bot text output.

    User speech: TranscriptionFrame (finalized STT output)
    Bot speech: TextFrame chunks between LLMFullResponseStart/End
    """

    def __init__(self, soldier_id: str, state_url: str, **kwargs):
        super().__init__(**kwargs)
        self.soldier_id = soldier_id
        self.state_url = state_url
        self._bot_buffer = ""
        self._buffering = False

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # Capture finalized user speech (downstream = from STT toward LLM)
        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            if frame.text and frame.text.strip():
                logger.info(f"[transcript] USER ({self.soldier_id}): {frame.text.strip()}")
                await self._post_transcript("user", frame.text.strip())

        # Capture bot response text (downstream = from LLM toward TTS)
        if isinstance(frame, LLMFullResponseStartFrame):
            self._bot_buffer = ""
            self._buffering = True

        if isinstance(frame, TextFrame) and self._buffering:
            self._bot_buffer += frame.text

        if isinstance(frame, LLMFullResponseEndFrame):
            self._buffering = False
            if self._bot_buffer.strip():
                logger.info(f"[transcript] BOT ({self.soldier_id}): {self._bot_buffer.strip()}")
                await self._post_transcript("bot", self._bot_buffer.strip())
            self._bot_buffer = ""

        await self.push_frame(frame, direction)

    async def _post_transcript(self, speaker: str, text: str):
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(
                    f"{self.state_url}/api/transcript",
                    json={
                        "soldier_id": self.soldier_id,
                        "speaker": speaker,
                        "text": text,
                    },
                )
        except Exception as e:
            logger.warning(f"Failed to post transcript: {e}")
