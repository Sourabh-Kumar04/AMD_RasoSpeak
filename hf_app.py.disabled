"""
RasoSpeak — Your Secondary Brain & AI Partner
HuggingFace Space - Connects to AMD MI300X endpoint
"""

import os
import gradio as gr
from openai import OpenAI

# Connect to your AMD MI300X endpoint
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")

client = OpenAI(base_url=VLLM_BASE_URL, api_key="not-required")


def chat(message, history):
    messages = [{"role": "system", "content": "You are RasoSpeak - a helpful AI partner with perfect memory. You can switch providers and answer questions about past conversations."}]

    for item in history:
        if isinstance(item, dict):
            messages.append({"role": item["role"], "content": item["content"]})
        else:
            messages.append({"role": "user", "content": item[0]})
            if item[1]:
                messages.append({"role": "assistant", "content": item[1]})

    messages.append({"role": "user", "content": message})

    stream = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        stream=True,
    )

    partial = ""
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            partial += delta
            yield partial


# Create Gradio interface
demo = gr.ChatInterface(
    fn=chat,
    title="RasoSpeak - Your Secondary Brain & AI Partner",
    description="14 AI agents on AMD MI300X | Wake word 'Hey Raso' | Perfect memory | Provider switching",
    examples=[
        "What's my name?",
        "What did I say about AI?",
        "Use ChatGPT for next question"
    ],
    cache_examples=False,
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)