import pywhatkit
import chainlit as cl
from agents import Agent, Runner, SQLiteSession , function_tool
from openai.types.responses import ResponseTextDeltaEvent
from model_config import model_config
from tools import web_search , send_user_email
import fitz #for pdf
from dotenv import load_dotenv
load_dotenv()


session = SQLiteSession("ai_email", "conversations.db")
config = model_config()

# 📄 Product Catalog Tool
@function_tool
async def products():
    """Return product list extracted from PDF 📄 with emojis."""
    file_path = "dummy_products.pdf"
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text("text") + "\n"
        doc.close()

        if not text.strip():
            return "⚠️ Sorry, product catalog is empty."
        
        return f"🛍️ Here's our latest product catalog with prices! 🌟\n\n{text}"

    except FileNotFoundError:
        return "⚠️ Product catalog not found."
    except Exception as e:
        return f"❌ Error extracting product catalog: {e}"

# 🧹 History Clean Tool
@function_tool
async def clean_history(confrom):
    """Clear chat history if user confirms."""
    if confrom.lower() == "yes":
        await session.clear_session()
        return "✅ Chat history cleared successfully! 🧹"
    else:
        return "❌ History not cleared. 💾"

# 📧 Email Content Generator
@function_tool
def generate_email_content(subject: str):
    """
    Generate a polite & professional email draft 📧.
    - User only gives subject.
    - Tool will auto-generate a friendly body.
    """
    body = (
        f"Hello 👋,\n\n"
        f"Thank you for your message regarding *{subject}*. 💡\n\n"
        "We’ve noted your concern and our team will get back to you soon with more details. 🚀\n\n"
        "Best regards,\nYour Support Team 💌"
    )
    return f"📧 Subject: {subject}\n\n{body}"


@function_tool
def support():
    """You're a support agent give support number to user with some attractive contact lines."""
    return f"OWNER : ASAD SHABIR \n\n Contact: +92353939049"


summarize_agent = Agent(
    name="SummarizeAgent",
    instructions="You're a summarization agent. Summarize the provided text comprehensively and accurately, capturing all details and main points in a highly structured and stylish format. Use bullet points with sub-bullets where necessary for clarity, ensuring no data is missed. Highlight important details using **bold text** and emphasize critical information with *italics*. Present the summary in a visually appealing layout, prioritizing readability and completeness. Respond in Urdu if the user prefers it. 😊",
)

# 🟢 WhatsApp Messaging Tool
@function_tool
def send_whatsapp_message(phone_number: str, message: str):
    """
    Send a WhatsApp message instantly using WhatsApp Web 📲.  
    - phone_number: Include country code (e.g., +923001234567)  
    - message: The text message to send  
    """
    try:
        pywhatkit.sendwhatmsg_instantly(
            phone_no=phone_number,
            message=message,
            wait_time=5,    # seconds to wait before sending
            tab_close=True  # close the tab automatically
        )
        return f"✅ WhatsApp message sent to {phone_number}! 📩"
    except Exception as e:
        return f"❌ Failed to send WhatsApp message: {str(e)}"

# 🎯 Main Agent
main_agent = Agent(
    name="EmailTaskAgent",
    instructions="""
You are a friendly **Email & Task Manager Agent** 🤖💌.
Your job is to:
- Generate email drafts (📧)
- Send emails (📨)
- Share product catalog (📄)
- Clear history (🧹)

⚡ Rules:
- Always include emojis in your responses.
- Do NOT explain tool calls — just return final results.
- Handle all requests dynamically & politely.
""",
    tools=[send_whatsapp_message,web_search,products, send_user_email, clean_history, generate_email_content, support],
)

# 🚀 Starter Messages


@cl.set_starters
async def set_starters():
    return [
        cl.Starter(label="📧 Draft Email", message="Make a draft email about products."),
        cl.Starter(label="🛍️ Show Catalog", message="Show me your product catalog."),
        cl.Starter(label="🧹 Reset Chat", message="Clear my history."),
        cl.Starter(label="❓ Support", message="Send Support Number?")
    ]

# 📄 File Reader Helper
def extract_text_from_pdf(file_path: str) -> str:
    text = ""
    try:
        doc = fitz.open(file_path)
        for page in doc:
            text += page.get_text("text") + "\n"
        doc.close()
    except Exception as e:
        text = f"⚠️ Error extracting text: {e}"
    return text

# 💬 Chat Handler
@cl.on_message
async def handle_message(message: cl.Message):
    msg = cl.Message(content="🤔 Thinking...⏳")
    await msg.send()

    # 🗂️ File uploads
    # 🗂️ Handle file uploads
    if message.elements:
        for element in message.elements:
            if isinstance(element, cl.File):
                file_path = element.path
                if not file_path:
                    await cl.Message(content="⚠️ File path not found.").send()
                    continue

                lower = file_path.lower()
                text = None  # default
                try:
                    if lower.endswith((".pdf", ".docx", ".txt")):
                        text = extract_text_from_pdf(file_path)
                except Exception as e:
                    await cl.Message(
                        content=f"❌ Error while extracting text: {str(e)}"
                    ).send()
                    continue

                if not text:
                    await cl.Message(content="⚠️ No text extracted from file.").send()
                    continue

                # Run summarizer on extracted text
                result = Runner.run_streamed(
                    summarize_agent,
                    input=text,
                    run_config=config,
                    session=session,
                )

                async for event in result.stream_events():
                    if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                        await msg.stream_token(event.data.delta)

                msg.content = result.final_output
                await msg.update()

        return  # ✅ stop after file handling
    
    # Normal chatbot flow
    response = Runner.run_streamed(
        main_agent,
        input=message.content,
        session=session,
        run_config=config,
    )

    async for event in response.stream_events():
        if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
            await msg.stream_token(event.data.delta)

    msg.content = response.final_output
    await msg.update()
