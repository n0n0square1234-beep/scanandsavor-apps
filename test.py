from anthropic import Anthropic

client = Anthropic(api_key="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")

message = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Give me a recipe using chicken and pasta."}
    ]
)

print(message.content[0].text)