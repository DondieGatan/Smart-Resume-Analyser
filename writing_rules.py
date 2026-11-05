"""House rules for AI-written text, shared by the AI tools and the builder assistant so both sound the same: plain
everyday words, no stock phrases, only ordinary keyboard characters. The prompts carry these rules; text_cleanup
enforces the character part afterwards, and stock_phrases_in() lets a caller check what the model still used."""

STOCK_PHRASES = (
    'i am writing to', 'i am excited to apply', 'passionate', 'dynamic', 'thrilled', 'leverage', 'leveraging',
    'synergy', 'fast-paced', 'proven track record', 'proven ability', 'results-driven', 'team player',
    'go above and beyond', 'i am confident that', 'valuable asset', "in today's", 'innovative', 'cutting-edge',
    'eager to', 'esteemed', 'aligns with', 'aligns well', 'directly aligns', 'directly matches',
    'demonstrating my', 'showcasing', 'robust', 'as specified', 'job description', 'earliest convenience',
    'strong match', 'great fit', 'ensuring code quality', 'enhancing user experience',
)

HUMAN_RULES = (
    'Write the way a real person writes: everyday words, and a mix of short and longer sentences. Prefer '
    'simple active verbs ("I built", "I fixed") over "I was responsible for". Do not tack a vague benefit '
    'onto the end of a sentence ("ensuring code quality", "enhancing user experience"); say what actually '
    'happened instead. Do not use any of these stock phrases or words: '
    + ', '.join(f'"{p}"' for p in STOCK_PHRASES) + '. '
    'Use only ordinary keyboard characters: letters, digits and . , ; : \' " ( ) ? ! - / @ %. Never use '
    'em dashes, en dashes, curly quotes, the ellipsis symbol, bullet symbols, arrows, emojis or any other '
    'special symbol. Where you would use a dash, use a comma or start a new sentence. '
)


def stock_phrases_in(text):
    low = (text or '').lower()
    return [p for p in STOCK_PHRASES if p in low]
