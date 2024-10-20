import threading
import time
from abc import ABC, abstractmethod
from queue import Queue
from typing import Optional

import librosa
import numpy as np
import pyaudio

from .config import CHANNELS, FEATURE_TYPE, FRAME_PER_SEG, HOP_LENGTH, SAMPLE_RATE
from .utils import process_chroma, process_chroma_decay


class BaseAudioStream(ABC):
    @abstractmethod
    def __init__(self, *args, **kwargs):
        pass

    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_value, traceback):
        pass

    @abstractmethod
    def _process_frame(self, data, frame_count, time_info, status_flag):
        pass

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def stop(self):
        pass


class AudioStreamThread(threading.Thread, BaseAudioStream):
    """
    A class to process audio stream in real-time

    Parameters
    ----------
    sample_rate : int
        Sample rate of the audio stream
    hop_length : int
        Hop length of the audio stream
    queue : Queue
        Queue to store the processed audio
    features : List[str]
        List of features to be processed
    chunk_size : int
        Size of the audio chunk
    """

    def __init__(
        self,
        feature_type: str = FEATURE_TYPE,
        sample_rate: int = SAMPLE_RATE,
        hop_length: int = HOP_LENGTH,
        chunk_size: int = FRAME_PER_SEG,
    ):
        threading.Thread.__init__(self)
        self.feature_type = feature_type
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.chunk_size = chunk_size * self.hop_length
        self.queue = Queue()
        self.audio_interface = None
        self.audio_stream: Optional[pyaudio.Stream] = None
        self.last_chunk = None
        self.init_time = None
        self.elapsed_times = []

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def initialize_audio_device(self):
        self.audio_interface = pyaudio.PyAudio()
        self.audio_stream = self.audio_interface.open(
            format=pyaudio.paFloat32,
            channels=CHANNELS,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._process_frame,
        )

    def _process_frame(self, data, frame_count, time_info, status_flag):
        target_audio = np.frombuffer(data, dtype=np.float32)  # initial y
        self._process_feature(target_audio, time_info["input_buffer_adc_time"])

        return (data, pyaudio.paContinue)

    def _process_feature(self, target_audio, f_time):
        if self.last_chunk is None:  # add zero padding at the first block
            target_audio = np.concatenate(
                (np.zeros(self.hop_length, dtype=np.float32), target_audio)
            )
        else:
            # add last chunk for continuity between chunks (overlap)
            target_audio = np.concatenate((self.last_chunk, target_audio))

        features_array = None
        if self.feature_type == "chroma":
            features_array = process_chroma(
                target_audio, self.sample_rate, self.hop_length, 2 * self.hop_length
            )
        elif self.feature_type == "chroma_decay":
            features_array = process_chroma_decay(
                target_audio, self.sample_rate, self.hop_length, 2 * self.hop_length
            )

        self.elapsed_times.append(time.time() - f_time)
        self.queue.put(
            (features_array, time.time())
        )  # update time after feature extraction
        self.last_chunk = target_audio[-self.hop_length :]
        print(f"feature shape: {type(features_array)}")

    @property
    def current_time(self):
        """
        Get current time since starting to listen
        """
        return time.time() - self.init_time if self.init_time else None

    def clear_queue(self):
        if self.queue.not_empty:
            self.queue.queue.clear()

    def run(self):
        self.clear_queue()
        self.initialize_audio_device()
        self.audio_stream.start_stream()
        print("* Start listening to audio stream....")
        self.init_time = self.audio_stream.get_time()

    def stop(self):
        print("* Stop listening to audio stream....")
        self.audio_stream.stop_stream()
        self.audio_stream.close()
        self.audio_interface.terminate()


class MockAudioStreamThread(AudioStreamThread):
    """
    A class to process audio stream from a file

    Parameters
    ----------
    file_path : str
        Path to the audio file
    """

    def __init__(
        self,
        file_path: str = "",
        feature_type: str = FEATURE_TYPE,
        sample_rate: int = SAMPLE_RATE,
        hop_length: int = HOP_LENGTH,
        chunk_size: int = FRAME_PER_SEG,
    ):
        super().__init__(
            sample_rate=sample_rate,
            hop_length=hop_length,
            feature_type=feature_type,
            chunk_size=chunk_size,
        )
        self.file_path = file_path

    def mock_stream(self):
        duration = int(librosa.get_duration(path=self.file_path))
        time_interval = self.chunk_size / self.sample_rate  # 0.0333 sec
        audio_y, _ = librosa.load(self.file_path, sr=self.sample_rate)
        padded_audio = np.concatenate(  # zero padding at the end
            (
                audio_y,
                np.zeros(int(duration * 0.1 * self.sample_rate), dtype=np.float32),
            )
        )
        trimmed_audio = padded_audio[  # trim to multiple of chunk_size
            : len(padded_audio) - (len(padded_audio) % self.chunk_size)
        ]
        while trimmed_audio.any():
            target_audio = trimmed_audio[: self.chunk_size]
            # print(f"time interval: {time_interval}")
            f_time = time.time()
            self.last_time = f_time
            self._process_feature(target_audio, f_time)
            trimmed_audio = trimmed_audio[self.chunk_size :]
            time.sleep(time_interval)

    def run(self):
        self.clear_queue()
        print(f"* [Mocking] Loading existing audio file({self.file_path})....")
        self.mock_stream()

    def stop(self):
        self.join()


class AudioStream:
    def __init__(
        self,
        feature_type="chroma",
        file_path=None,
        sample_rate=SAMPLE_RATE,
        hop_length=HOP_LENGTH,
        chunk_size=FRAME_PER_SEG,
    ):
        self.file_path = file_path
        self.feature_type = feature_type
        self.sample_rate = sample_rate
        self.hop_length = hop_length
        self.chunk_size = chunk_size

        if self.file_path:
            self.stream = MockAudioStreamThread(
                file_path=self.file_path,
                feature_type=self.feature_type,
                sample_rate=self.sample_rate,
                hop_length=self.hop_length,
                chunk_size=self.chunk_size,
            )
        else:
            self.stream = AudioStreamThread(
                feature_type=self.feature_type,
                sample_rate=self.sample_rate,
                hop_length=self.hop_length,
                chunk_size=self.chunk_size,
            )

    def __enter__(self):
        self.stream.start()
        return self.stream

    def __exit__(self, exc_type, exc_value, traceback):
        self.stream.stop()

    def run(self):
        self.stream.run()

    def stop(self):
        self.stream.stop()
