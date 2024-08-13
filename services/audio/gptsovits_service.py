import datetime
import lzma
import os
import zipfile
from io import BytesIO

import numpy as np
import requests
import torch
from pydub import AudioSegment
from pydub.playback import play

from config.config import my_config
from tools.file_utils import read_file, convert_mp3_to_wav
from tools.utils import must_have_value, random_with_system_time
import streamlit as st
import pybase16384 as b14

# 获取当前脚本的绝对路径
script_path = os.path.abspath(__file__)

# print("当前脚本的绝对路径是:", script_path)

# 脚本所在的目录
script_dir = os.path.dirname(script_path)

# 音频输出目录
audio_output_dir = os.path.join(script_dir, "../../work")
audio_output_dir = os.path.abspath(audio_output_dir)


def encode_spk_emb(spk_emb: torch.Tensor) -> str:
    arr: np.ndarray = spk_emb.to(dtype=torch.float16, device="cpu").detach().numpy()
    s = b14.encode_to_string(
        lzma.compress(
            arr.tobytes(),
            format=lzma.FORMAT_RAW,
            filters=[{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME}],
        ),
    )
    del arr
    return s

class GPTSoVITSAudioService:
    def __init__(self):
        super().__init__()
        self.service_location = my_config['audio']['local_tts']['GPTSoVITS']['server_location']
        must_have_value(self.service_location, "请设置GPTSoVITS server location")
        self.service_location = self.service_location.rstrip('/') + '?'

        self.audio_temperature = st.session_state.get('audio_temperature')
        self.audio_top_p = st.session_state.get('audio_top_p')
        self.audio_top_k = st.session_state.get('audio_top_k')

        audio_speed = st.session_state.get("audio_speed")
        if audio_speed == "normal":
            self.audio_speed = "1.0"
        if audio_speed == "fast":
            self.audio_speed = "1.1"
        if audio_speed == "slow":
            self.audio_speed = "0.9"
        if audio_speed == "faster":
            self.audio_speed = "1.2"
        if audio_speed == "slower":
            self.audio_speed = "0.8"
        if audio_speed == "fastest":
            self.audio_speed = "1.3"
        if audio_speed == "slowest":
            self.audio_speed = "0.7"

        if st.session_state.get("use_reference_audio"):
            self.refer_wav_path= st.session_state.get("reference_audio")
            self.prompt_text = st.session_state.get("reference_audio_text")
            self.prompt_language = st.session_state.get("reference_audio_language")

        self.text_language = st.session_state.get("inference_audio_language")

    def read_with_content(self, content):
        wav_file = os.path.join(audio_output_dir, str(random_with_system_time()) + ".wav")
        temp_file = self.chat_with_content(content, wav_file)
        # 读取音频文件
        audio = AudioSegment.from_file(temp_file)
        play(audio)

    def chat_with_content(self, content, audio_output_file):
        # main infer params
        if self.refer_wav_path:
            body = {
                "text": [content],
                "refer_wav_path": self.refer_wav_path,
                "prompt_text": self.prompt_text,
                "prompt_language": self.prompt_language,
                "text_language": self.text_language,
                "top_k": self.audio_top_k,
                "top_p": self.audio_top_p,
                "temperature": self.audio_temperature,
                "speed": self.audio_speed,
            }
        else:
            body = {
                "text": [content],
                "text_language": self.text_language,
                "top_k": self.audio_top_k,
                "top_p": self.audio_top_p,
                "temperature": self.audio_temperature,
                "speed": self.audio_speed,
            }

        print(body)

        try:
            response = requests.post(self.service_location, json=body)
            response.raise_for_status()
            with zipfile.ZipFile(BytesIO(response.content), "r") as zip_ref:
                zip_ref.extractall(audio_output_dir)
                file_names = zip_ref.namelist()
                output_file = os.path.join(audio_output_dir, file_names[0])

                convert_mp3_to_wav(output_file, audio_output_file)
                print("Extracted files into", audio_output_file)
                return audio_output_file

        except requests.exceptions.RequestException as e:
            print(f"Request Error: {e}")
