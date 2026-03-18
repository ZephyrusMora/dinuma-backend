from app.services.db import get_active_tokens

tokens = get_active_tokens(None)
print('Total tokens in DB:', len(tokens))
for t in tokens:
    print(t[:50], '...')