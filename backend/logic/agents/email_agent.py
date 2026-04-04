"""
Email Agent — Gmail-powered specialist agent.
Handles reading, searching, sending, and replying to emails.

Tools:
  - read_emails: Get the N most recent emails
  - search_emails: Search emails by keyword/query
  - send_email: Compose and send a new email
  - reply_to_email: Reply to an existing thread
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import base64
import datetime
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from utils.main_utils import llm_model
# from core.lifespan import saver

logger = logging.getLogger(__name__)

today = datetime.datetime.now().strftime("%Y-%m-%d")

# ==========================================
# 1. Gmail OAuth Setup
# ==========================================

# Full scope: read + send + modify. Required for send/reply tools.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]

CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../client_secret.json'))
GMAIL_TOKEN_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../gmail_token.json'))


def _get_gmail_service():
    """Load or refresh Gmail OAuth tokens and return the service."""
    creds = None
    if os.path.exists(GMAIL_TOKEN_PATH):
        logger.info("Loading Gmail credentials from gmail_token.json")
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail credentials")
            creds.refresh(Request())
        else:
            logger.info("Initiating new Gmail OAuth flow")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8080)
        with open(GMAIL_TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def _parse_message(msg: dict) -> dict:
    """Extract human-readable fields from a raw Gmail message object."""
    headers = {h['name']: h['value'] for h in msg.get('payload', {}).get('headers', [])}
    snippet = msg.get('snippet', '')
    return {
        "id": msg['id'],
        "thread_id": msg.get('threadId'),
        "from": headers.get('From', 'Unknown'),
        "to": headers.get('To', 'Unknown'),
        "subject": headers.get('Subject', '(no subject)'),
        "date": headers.get('Date', ''),
        "snippet": snippet,
    }


# ==========================================
# 2. Gmail Tools
# ==========================================

@tool
def read_emails(n: int = 5, category: str = "primary") -> str:
    """
    Read the N most recent emails from the inbox.
    'n' is the number of emails to retrieve (default 5).
    'category' filters by Gmail inbox tab:
      - 'primary'    → Personal/direct emails (default)
      - 'promotions' → Deals, newsletters, offers
      - 'social'     → Facebook, Twitter, LinkedIn notifications
      - 'updates'    → Receipts, bills, confirmations
      - 'forums'     → Mailing lists, discussion boards
      - 'all'        → Everything in your inbox (no filter)
    """
    logger.info(f"Reading {n} most recent emails from category: '{category}'")
    service = _get_gmail_service()

    # Map friendly name → Gmail label ID
    CATEGORY_LABELS = {
        "primary":    "CATEGORY_PERSONAL",
        "promotions": "CATEGORY_PROMOTIONS",
        "social":     "CATEGORY_SOCIAL",
        "updates":    "CATEGORY_UPDATES",
        "forums":     "CATEGORY_FORUMS",
    }

    label_ids = ['INBOX']
    # cat_label = CATEGORY_LABELS.get(category.lower())
    # if cat_label:
    #     label_ids.append(cat_label)

    results = service.users().messages().list(
        userId='me',
        maxResults=n,
        labelIds=label_ids,
    ).execute()
    messages = results.get('messages', [])

    if not messages:
        return f"No emails found in your {category} inbox."

    tab_name = category.capitalize()
    output = f"Here are your {len(messages)} most recent emails from **{tab_name}**:\n\n"
    for msg_ref in messages:
        msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='metadata').execute()
        parsed = _parse_message(msg)
        output += (
            f"📧 ID: {parsed['id']}\n"
            f"   From: {parsed['from']}\n"
            f"   Subject: {parsed['subject']}\n"
            f"   Date: {parsed['date']}\n"
            f"   Preview: {parsed['snippet'][:120]}...\n\n"
        )
    return output


@tool
def search_emails(query: str) -> str:
    """Search emails using Gmail query syntax (e.g. 'from:boss@work.com', 'subject:invoice', 'is:unread')."""
    logger.info(f"Searching emails with query: '{query}'")
    service = _get_gmail_service()

    results = service.users().messages().list(userId='me', q=query, maxResults=10).execute()
    messages = results.get('messages', [])

    if not messages:
        return f"No emails found matching: '{query}'"

    output = f"Found {len(messages)} email(s) matching '{query}':\n\n"
    for msg_ref in messages:
        msg = service.users().messages().get(userId='me', id=msg_ref['id'], format='metadata').execute()
        parsed = _parse_message(msg)
        output += (
            f"📧 ID: {parsed['id']}\n"
            f"   From: {parsed['from']}\n"
            f"   Subject: {parsed['subject']}\n"
            f"   Date: {parsed['date']}\n"
            f"   Preview: {parsed['snippet'][:120]}...\n\n"
        )
    return output


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Compose and send a new email.
    'to' is the recipient email address.
    'subject' is the email subject line.
    'body' is the plain text email body.
    """
    logger.info(f"Sending email to '{to}' with subject '{subject}'")
    service = _get_gmail_service()

    message = MIMEMultipart()
    message['to'] = to
    message['subject'] = subject
    message.attach(MIMEText(body, 'plain'))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId='me', body={'raw': raw}).execute()
    logger.info(f"Email sent. Message ID: {sent['id']}")
    return f"Email sent successfully to {to}. Message ID: {sent['id']}"


@tool
def reply_to_email(message_id: str, body: str) -> str:
    """
    Reply to an existing email thread.
    'message_id' is the ID of the email to reply to (shown in read/search results).
    'body' is the plain text reply content.
    """
    logger.info(f"Replying to message ID: {message_id}")
    service = _get_gmail_service()

    # Fetch the original email to get thread info and headers
    original = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()
    headers = {h['name']: h['value'] for h in original.get('payload', {}).get('headers', [])}

    reply = MIMEMultipart()
    reply['to'] = headers.get('From', '')
    reply['subject'] = 'Re: ' + headers.get('Subject', '')
    reply['In-Reply-To'] = headers.get('Message-ID', '')
    reply['References'] = headers.get('Message-ID', '')
    reply.attach(MIMEText(body, 'plain'))

    raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
    thread_id = original.get('threadId')
    sent = service.users().messages().send(userId='me', body={'raw': raw, 'threadId': thread_id}).execute()
    logger.info(f"Reply sent. Message ID: {sent['id']}")
    return f"Reply sent successfully. Message ID: {sent['id']}"


# ==========================================
# 3. Setup the Email Agent
# ==========================================

email_tools = [read_emails, search_emails, send_email, reply_to_email]

rules_md = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/rules.md'))
user_preferences_md = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/user_preferences/preferences.md'))


def _safe_read_text(path: str, missing_message: str) -> str:
    """Read file content safely and return fallback text if missing/unreadable."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        logger.warning("Context file not found: %s", path)
        return missing_message
    except OSError:
        logger.exception("Failed to read context file: %s", path)
        return missing_message


def _build_email_system_prompt() -> str:
    """Build system prompt dynamically so updated preferences are picked up."""
    rules_text = _safe_read_text(rules_md, "No additional rules file found.")
    preferences_text = _safe_read_text(
        user_preferences_md,
        "No user preferences file found yet. Use neutral defaults and ask brief clarifying questions when needed.",
    )

    return f"""You are a helpful and careful email assistant.
Before you carry on with your tasks:
Read through and follow rules strictly.
{rules_text}

Tailor your responses to user's locale and preferences.
{preferences_text}

Today's date is {today}.

Your role is to help the user manage their email efficiently while ensuring accuracy, clarity, and user confirmation before taking any action.

GENERAL BEHAVIOR:
- Always be clear, polite, and concise in your responses.
- If any required information is missing, ask follow-up questions before proceeding.
- Never assume details such as recipients, subject lines, or intent without confirmation.

CORE RULES AND TOOL USAGE:

1. READ EMAILS (`read_emails`)
   - Use this tool when the user wants to view their inbox.
   - ALWAYS ask:
     a) How many emails they want to see (default to 5 if unspecified)
     b) Which inbox category/tab they want:
        - primary (personal)
        - promotions
        - social
        - updates
        - all
   - Clearly present the results in a readable format.

2. SEARCH EMAILS (`search_emails`)
   - Use this tool when the user is looking for specific emails.
   - You can search by:
     - keyword
     - sender
     - subject
     - status (e.g., "is:unread", "is:starred")
   - If the request is vague, ask clarifying questions before searching.

3. SEND EMAIL (`send_email`)
   - Use this tool ONLY when composing a brand new email.
   - You MUST collect and confirm the following before sending:
     - Recipient (To)
     - Subject line
     - Email body
   - Present the full draft to the user and explicitly ask for confirmation.
   - IMPORTANT: Once the user approves the draft, YOU MUST INVOKE THE `send_email` TOOL to actually send it. Never just write "Email sent" without calling the tool!

4. REPLY TO EMAIL (`reply_to_email`)
   - Use this tool when the user wants to reply to an existing email.
   - You MUST have the Message ID (from read/search results).
   - Draft the reply and show it to the user.
   - Explicitly ask for confirmation before sending.
   - IMPORTANT: Once the user approves, YOU MUST INVOKE THE `reply_to_email` TOOL.

SAFETY AND CONFIRMATION:
- NEVER send or reply to any email without explicit user confirmation.
- If the user gives partial instructions (e.g., “reply yes”), ask for clarification or draft a suggested response.
- When in doubt, confirm before acting.

Your priority is to assist accurately while giving the user full control over all outgoing communication.
"""


def _create_email_react_agent():
    """Create email agent with latest prompt context for each invocation."""
    return create_agent(
        model=llm_model,
        system_prompt=_build_email_system_prompt(),
        tools=email_tools,
        middleware=[HumanInTheLoopMiddleware(
            interrupt_on={
                "send_email": True,
                "reply_to_email": True,
                "read_emails": False,
                "search_emails": False,
            },
            description_prefix="Email action pending approval",
        )],
    )

# ==========================================
# 4. LangGraph Node Wrapper
# ==========================================

def email_worker_node(state: dict, config: RunnableConfig) -> dict:
    """LangGraph node that runs the email agent."""
    logger.info("📧 Email worker node invoked.")
    email_react_agent = _create_email_react_agent()

    response = email_react_agent.invoke(
        {"messages": state["messages"]},
        config=config
    )

    logger.info("📧 Email worker node finished.")
    messages = response.get("messages", []) if isinstance(response, dict) else []
    return {"messages": messages}


# ==========================================
# 5. Local Test
# ==========================================

if __name__ == "__main__":
    print("\n📧 Email Agent Chat (type 'quit' to exit)\n")

    config: RunnableConfig = {"configurable": {"thread_id": "email_test_1"}}
    user_input = input("You: ").strip()

    while True:
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        email_react_agent = _create_email_react_agent()

        response = email_react_agent.invoke(
            {"messages": [HumanMessage(content=user_input)]},
            config=config
        )

        if response and "messages" in response:
            print(f"\n📧 Agent: {response['messages'][-1].content}\n")

        # Check for HITL interrupts
        state_snapshot = email_react_agent.get_state(config)
        if state_snapshot.tasks and state_snapshot.tasks[0].interrupts:
            print("💥 [INTERRUPT]: Agent wants to send/reply to an email.")
            approval = input("Your decision (approve/reject): ").strip().lower()
            decision = "approve" if approval == "approve" else "reject"
            resume = email_react_agent.invoke(
                Command(resume={"decisions": [{"type": decision}]}),
                config=config
            )
            if resume and "messages" in resume:
                print(f"\n📧 Agent: {resume['messages'][-1].content}\n")

        user_input = input("You: ").strip()