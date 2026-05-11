"""
RasoSpeak — Your Secondary Brain & AI Partner
Hugging Face Space

Full-featured Gradio interface with all capabilities.
"""

import os
import json
import time

import gradio as gr
import httpx

# Configuration from environment
VLLM_HOST = os.getenv("VLLM_HOST", "localhost")
VLLM_PORT = int(os.getenv("VLLM_PORT", "8001"))
VLLM_BASE_URL = f"http://{VLLM_HOST}:{VLLM_PORT}/v1"

# API Keys (from environment)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# State
current_script = ""
partner_active = False


# ══════════════════════════════════════════════════════
# BACKEND HELPERS
# ══════════════════════════════════════════════════════

def check_backend_status():
    """Check if backend services are available."""
    status = {"vllm": False, "whisper": False}

    try:
        client = httpx.Client(timeout=5)
        resp = client.get(f"{VLLM_BASE_URL}/models")
        status["vllm"] = resp.status_code == 200
    except Exception:
        pass

    return status


def get_available_providers():
    """Check which AI providers are available."""
    providers = []

    if VLLM_BASE_URL:
        try:
            client = httpx.Client(timeout=5)
            resp = client.get(f"{VLLM_BASE_URL}/models")
            if resp.status_code == 200:
                providers.append("💻 Local Qwen (vLLM)")
        except Exception:
            pass

    if OPENAI_API_KEY:
        providers.append("🔵 OpenAI GPT")

    if ANTHROPIC_API_KEY:
        providers.append("🟣 Anthropic Claude")

    if GOOGLE_API_KEY:
        providers.append("🟢 Google Gemini")

    if not providers:
        providers.append("⚠️ Using local Qwen only")

    return providers


def call_api(endpoint, data=None, method="POST"):
    """Make API call to backend."""
    try:
        client = httpx.Client(timeout=30)
        url = f"http://localhost:8000{endpoint}"

        if method == "GET":
            resp = client.get(url)
        else:
            resp = client.post(url, json=data)

        if resp.status_code == 200:
            return resp.json()
        return {"error": f"Status {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ══════════════════════════════════════════════════════
# AI CHAT FUNCTIONS
# ══════════════════════════════════════════════════════

def ask_ai(question, provider="qwen", include_context=True):
    """Ask the AI partner a question."""
    result = call_api("/partner/ask", {
        "message": question,
        "provider": provider
    })
    return result.get("answer", result.get("error", "Error"))


def ask_with_context(question, context, provider="qwen"):
    """Ask with additional context."""
    result = call_api("/qa", {
        "question": question,
        "provider": provider,
        "context": context,
        "stream_to_earpiece": True
    })
    return result.get("answer", result.get("error", "Error"))


def switch_provider(provider, temporary=False):
    """Switch AI provider."""
    result = call_api(f"/partner/provider?provider={provider}&temporary={temporary}", method="POST")
    return result.get("message", "Done")


def search_web(query):
    """Search the web."""
    result = call_api("/search", {
        "query": query,
        "num_results": 5,
        "include_summary": True
    })
    return result.get("summary", result.get("error", "No results"))


# ══════════════════════════════════════════════════════
# PARTNER / MEMORY FUNCTIONS
# ══════════════════════════════════════════════════════

def start_partner_mode():
    """Start continuous partner mode."""
    global partner_active
    result = call_api("/partner/start", {})
    partner_active = True
    return result.get("message", "Partner mode started")


def stop_partner_mode():
    """Stop partner mode."""
    global partner_active
    result = call_api("/partner/stop", {})
    partner_active = False
    return result.get("message", "Partner mode stopped")


def get_partner_status():
    """Get partner status."""
    result = call_api("/partner/status", method="GET")
    return json.dumps(result, indent=2)


def query_memory(query):
    """Query past conversations."""
    result = call_api(f"/partner/query?query={query}", method="GET")
    return result.get("summary", "No memories found")


def get_memory_stats():
    """Get memory statistics."""
    result = call_api("/memory/stats", method="GET")
    return json.dumps(result, indent=2)


# ══════════════════════════════════════════════════════
# DOCUMENT IMPORT
# ══════════════════════════════════════════════════════

def import_text_note(content, title="", category="note"):
    """Import text to memory."""
    result = call_api("/documents/text", {
        "content": content,
        "title": title,
        "category": category,
        "tags": []
    })
    return f"Imported: {result.get('title', 'Note')}"


def import_url_content(url):
    """Import URL to memory."""
    result = call_api("/documents/url", {"url": url})
    return result.get("title", "Imported")


def list_documents():
    """List imported documents."""
    result = call_api("/documents", method="GET")
    docs = result.get("documents", [])
    if not docs:
        return "No documents imported yet."
    return "\n".join([f"- {d.get('title', 'Untitled')}" for d in docs[:10]])


def search_documents(query):
    """Search imported documents."""
    result = call_api(f"/documents/search?query={query}", method="GET")
    results = result.get("results", [])
    if not results:
        return "No matches found."
    return "\n".join([f"- {r.get('title', 'Doc')}: {r.get('snippet', '')[:100]}..." for r in results[:5]])


# ══════════════════════════════════════════════════════
# REMINDERS
# ══════════════════════════════════════════════════════

def set_reminder(message, remind_at="in 1 hour"):
    """Set a reminder."""
    result = call_api("/partner/reminder", {
        "message": message,
        "remind_at": remind_at
    })
    return f"Reminder set: {message}"


def get_reminders():
    """Get all reminders."""
    result = call_api("/partner/reminders", method="GET")
    active = result.get("active", [])
    if not active:
        return "No active reminders."
    return "\n".join([f"⏰ {r.get('message')} (at {r.get('remind_at')})" for r in active])


# ══════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════

def send_notification(title, message):
    """Send a notification."""
    result = call_api("/notifications/send", {
        "title": title,
        "message": message,
        "priority": "normal"
    })
    return f"Sent to: {', '.join(result.get('channels', ['some channels']))}"


# ══════════════════════════════════════════════════════
# GRADIO INTERFACE
# ══════════════════════════════════════════════════════

with gr.Blocks(title="RasoSpeak — Your Secondary Brain & AI Partner", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🎙️ RasoSpeak — Your Secondary Brain & AI Partner
    ### Powered by AMD MI300X | 14 AI Agents | "Hey Raso" Wake Word

    Your continuous AI companion that remembers everything,
    answers questions, imports documents, and sends notifications.
    """)

    with gr.Tab("🤖 AI Partner"):
        gr.Markdown("### Ask your AI partner anything")

        with gr.Row():
            with gr.Column():
                provider_dropdown = gr.Dropdown(
                    ["qwen", "openai", "anthropic", "gemini"],
                    value="qwen",
                    label="AI Provider",
                    info="Select which AI to use"
                )
                question_input = gr.Textbox(
                    label="Ask a Question",
                    placeholder="What's the meaning of life? OR use ChatGPT for next questions...",
                    lines=2
                )
                ask_btn = gr.Button("Ask", variant="primary")

            with gr.Column():
                answer_output = gr.Textbox(label="Answer", lines=6)

        ask_btn.click(ask_ai, inputs=[question_input, provider_dropdown], outputs=[answer_output])

        gr.Markdown("---")
        gr.Markdown("### Switch Provider")
        with gr.Row():
            switch_btn = gr.Button("Switch to Selected", variant="secondary")
            switch_status = gr.Textbox(label="Status", interactive=False)
        switch_btn.click(switch_provider, inputs=[provider_dropdown], outputs=[switch_status])

        gr.Markdown("---")
        gr.Markdown("### Web Search")
        with gr.Row():
            search_input = gr.Textbox(label="Search Query", placeholder="Latest AI news...")
            search_btn = gr.Button("Search")
        search_output = gr.Textbox(label="Results", lines=4)
        search_btn.click(search_web, inputs=[search_input], outputs=[search_output])

    with gr.Tab("🧠 Partner Mode"):
        gr.Markdown("### Your AI Partner - Continuous Companion")

        with gr.Row():
            start_btn = gr.Button("▶️ Start Partner Mode", variant="primary")
            stop_btn = gr.Button("⏹️ Stop Partner Mode", variant="stop")

        status_output = gr.Textbox(label="Status", lines=3)

        start_btn.click(start_partner_mode, outputs=[status_output])
        stop_btn.click(stop_partner_mode, outputs=[status_output])

        gr.Markdown("---")
        gr.Markdown("### Query Your Memory")
        with gr.Row():
            memory_query = gr.Textbox(
                label="Search Past Conversations",
                placeholder="What did I say about AI? When did I talk about..."
            )
            query_btn = gr.Button("Search Memory")
        memory_output = gr.Textbox(label="Results", lines=5)

        query_btn.click(query_memory, inputs=[memory_query], outputs=[memory_output])

        gr.Markdown("---")
        gr.Markdown("### Memory Stats")
        stats_btn = gr.Button("📊 Get Memory Stats")
        stats_output = gr.Textbox(label="Statistics", lines=8)
        stats_btn.click(get_memory_stats, outputs=[stats_output])

    with gr.Tab("📄 Documents"):
        gr.Markdown("### Import Documents to Memory")

        gr.Markdown("#### Import Text Note")
        with gr.Row():
            text_content = gr.Textbox(label="Content", lines=3, placeholder="Paste your notes here...")
            text_title = gr.Textbox(label="Title (optional)")
        import_text_btn = gr.Button("Import Text")
        import_status = gr.Textbox(label="Status")

        import_text_btn.click(import_text_note, inputs=[text_content, text_title], outputs=[import_status])

        gr.Markdown("#### Import from URL")
        with gr.Row():
            url_input = gr.Textbox(label="URL", placeholder="https://...")
        import_url_btn = gr.Button("Import URL")
        import_url_status = gr.Textbox(label="Status")

        import_url_btn.click(import_url_content, inputs=[url_input], outputs=[import_url_status])

        gr.Markdown("---")
        gr.Markdown("### Search Documents")
        with gr.Row():
            doc_search = gr.Textbox(label="Search", placeholder="Search imported documents...")
            doc_search_btn = gr.Button("Search")
        doc_results = gr.Textbox(label="Results", lines=5)

        doc_search_btn.click(search_documents, inputs=[doc_search], outputs=[doc_results])

        gr.Markdown("---")
        gr.Markdown("### All Documents")
        list_btn = gr.Button("📋 List All Documents")
        list_output = gr.Textbox(label="Documents", lines=6)

        list_btn.click(list_documents, outputs=[list_output])

    with gr.Tab("⏰ Reminders"):
        gr.Markdown("### Reminders")

        with gr.Row():
            reminder_msg = gr.Textbox(label="Reminder", placeholder="Call mom...")
            reminder_time = gr.Textbox(label="When", value="in 1 hour")
        set_reminder_btn = gr.Button("Set Reminder")

        reminder_status = gr.Textbox(label="Status")
        set_reminder_btn.click(set_reminder, inputs=[reminder_msg, reminder_time], outputs=[reminder_status])

        gr.Markdown("---")
        gr.Markdown("### Active Reminders")
        get_reminders_btn = gr.Button("🔔 Get Reminders")
        reminders_output = gr.Textbox(label="Reminders", lines=5)

        get_reminders_btn.click(get_reminders, outputs=[reminders_output])

    with gr.Tab("📱 Notifications"):
        gr.Markdown("### Send Notifications")

        with gr.Row():
            notif_title = gr.Textbox(label="Title")
            notif_msg = gr.Textbox(label="Message")
        send_notif_btn = gr.Button("📤 Send Notification")

        notif_status = gr.Textbox(label="Status")
        send_notif_btn.click(send_notification, inputs=[notif_title, notif_msg], outputs=[notif_status])

    with gr.Tab("⚙️ Settings"):
        gr.Markdown("### System Status")

        status = check_backend_status()
        providers = get_available_providers()

        gr.Markdown(f"**Backend Status:**")
        gr.Markdown(f"- vLLM: {'✅ Available' if status['vllm'] else '❌ Not available'}")

        gr.Markdown(f"**Available AI Providers:**")
        for p in providers:
            gr.Markdown(f"- {p}")

        gr.Markdown("""
        ---
        ### Environment Variables (for full features)

        Set these in your Space secrets:
        - `OPENAI_API_KEY` - For GPT-4
        - `ANTHROPIC_API_KEY` - For Claude
        - `GOOGLE_API_KEY` - For Gemini
        - `TELEGRAM_BOT_TOKEN` - For notifications

        ### Wake Word
        Say **"Hey Raso"** to activate your AI partner!
        """)

    gr.Markdown("""
    ---
    *Built for AMD Developer Hackathon × lablab.ai*
    *Powered by AMD Instinct MI300X + ROCm | 14 AI Agents*
    """)


# Launch the Space
if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("PORT", "7860")),
        share=True
    )