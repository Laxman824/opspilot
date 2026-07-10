"""Sample requests: the simulated inbox and the batch-demo CSV.

Note: #1 and #10 share a sender on purpose — processing #1 then #10 demonstrates
the agent's sender memory (urgency bump + supervisor alert on the repeat complaint).
#9 is deliberately ambiguous to demonstrate the low-confidence human-review gate.
"""
from __future__ import annotations

import csv
import os

SAMPLE_INBOX = [
    {
        "sender": "priya.sharma@example.com",
        "subject": "Charged twice on my June invoice",
        "body": ("Hello, I just checked my June invoice and I've been charged twice "
                 "for the same monthly plan — two debits of Rs. 1,499 on the same day. "
                 "I've been a customer for three years and this is disappointing. "
                 "Please correct the invoice and confirm the extra charge will be "
                 "reversed. I'd like a response soon."),
    },
    {
        "sender": "arun.mehta@example.com",
        "subject": "Technician did not show up - twice",
        "body": ("This is the second appointment your technician has missed without "
                 "any call or message. I took time off work both days and waited the "
                 "entire slot. This is really poor service and honestly unacceptable. "
                 "I need this repair completed and someone to explain why this keeps "
                 "happening."),
    },
    {
        "sender": "sneha.rao@example.com",
        "subject": "Question about payment options",
        "body": ("Hi team, quick question — which payment methods do you accept for "
                 "monthly invoices, and on what date is the invoice usually issued? "
                 "I want to set up an auto-payment from my bank. Thanks!"),
    },
    {
        "sender": "vikram.iyer@example.com",
        "subject": "How do I reset my portal password?",
        "body": ("Hello, I can't log in to the customer portal anymore — I think I "
                 "forgot my password. Could you tell me how to reset it? Is there a "
                 "self-service option or do I need to call support?"),
    },
    {
        "sender": "kavya.nair@example.com",
        "subject": "New broadband installation at my new flat",
        "body": ("Hi, I'm moving to a new flat next week and would like to schedule a "
                 "broadband installation there. My account reference is ACC-2231. The "
                 "new address is 14B, Lakeview Residency, Whitefield. I'd prefer a "
                 "weekend slot if possible. Please confirm the appointment."),
    },
    {
        "sender": "rahul.desai@example.com",
        "subject": "Upgrade my plan to Premium",
        "body": ("Hello, I'd like to upgrade my current Basic plan to the Premium plan "
                 "starting from the next billing cycle. My account is under this email. "
                 "Please process the change and confirm the new monthly amount."),
    },
    {
        "sender": "meera.pillai@example.com",
        "subject": "NO SERVICE FOR 3 DAYS - cancelling if not fixed today",
        "body": ("My connection has been completely dead for three days. I work from "
                 "home and have already lost client meetings. I've called twice and "
                 "nobody has fixed it. If this is not resolved TODAY I am cancelling "
                 "my contract and filing a complaint with the consumer forum. This is "
                 "my final warning."),
    },
    {
        "sender": "suresh.kumar@example.com",
        "subject": "Fifth attempt to reach you - next step is my lawyer",
        "body": ("This is now the FIFTH time I am contacting you about the same unresolved "
                 "billing issue. Every time I'm told someone will call back and nobody "
                 "ever does. I've had enough. If I don't get a real resolution this "
                 "week, my lawyer will be in touch. Treat this as formal notice."),
    },
    {
        "sender": "ananya.gupta@example.com",
        "subject": "Bill looks different + want to add a second line",
        "body": ("Hi, my bill looks different this month and I'm not sure why — the "
                 "amount is higher than usual. Also, while I have your attention, I "
                 "want to add a second line to my account for my son. Can someone "
                 "explain the bill and help me set that up?"),
    },
    {
        "sender": "priya.sharma@example.com",
        "subject": "Overcharged AGAIN - second month in a row",
        "body": ("I can't believe I'm writing this again. This is the second month in "
                 "a row you have overcharged me on my invoice. Last month's double "
                 "charge was supposed to be fixed, and now the new invoice is wrong "
                 "too. I expect this corrected immediately and an explanation of how "
                 "this happened twice."),
    },
]

CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "sample_requests.csv")


def write_sample_csv(path: str = CSV_PATH) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sender", "subject", "body"])
        writer.writeheader()
        writer.writerows(SAMPLE_INBOX)
    return path


if __name__ == "__main__":
    print(f"wrote {write_sample_csv()}")
