from dataclasses import dataclass
import sys

from services.local_ai_service import local_ai_reply


@dataclass
class DemoUser:
    whatsapp_id: str = "919999999999"
    language: str = "en"


def main():
    user = DemoUser()

    questions = sys.argv[1:]
    if questions:
        questions = [" ".join(questions)]
    else:
        questions = [
            "My company has not paid salary for two months. What can I do?",
            "I paid online but the seller is not giving refund.",
            "Police called me for a false FIR. What should I do?",
            "I have a flat possession issue with builder.",
        ]

    print("NyaySetu local AI demo")
    print("No OpenAI key. No Claude key.")
    print("Optional: set LOCAL_AI_PROVIDER=ollama to use local Ollama.\n")

    for idx, question in enumerate(questions, start=1):
        print("=" * 72)
        print(f"User question {idx}: {question}\n")
        print(local_ai_reply(question, user=user, context="general"))
        print()


if __name__ == "__main__":
    main()
