"""Turns model replies into plain, human-looking text. Shared by the AI tools and the builder assistant, so every
AI answer in the app is cleaned the same way: markdown removed, and typographic or decorative characters (em and
en dashes, curly quotes, ellipsis, bullet symbols, arrows, emojis, odd spaces) replaced by ordinary keyboard
characters. Letters from any language, including accented ones, are left alone."""
import re

_MARKDOWN_JUNK = re.compile(r'(\*\*|__|`{1,3})')
_HEADING = re.compile(r'^\s{0,3}#{1,6}\s*', re.M)


_EMOJI = re.compile('[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍™®©]')
_BULLET_SYMBOLS = '•●▪◦‣⁃■▫∙·'
_QUOTES = {'‘': "'", '’': "'", '‚': "'", '‛': "'", '′': "'",
           '“': '"', '”': '"', '„': '"', '‟': '"', '″': '"', '«': '"', '»': '"'}
_SPACES = '            　'
_INVISIBLE = '​‌⁠﻿­'
_ARROWS = '→⇒➜➡➔⇨'
_REPLACEMENTS = {'…': '...', '×': 'x', '≈': '~', '≥': '>=', '≤': '<=', '≠': '!=',
                 '−': '-', '‐': '-', '‑': '-', '‒': '-'}


def plain_text(text):
    """Turns typographic and decorative characters into ordinary keyboard ones (em dashes, curly quotes, bullet
    symbols, arrows, emojis, odd spaces), so the reply reads like something typed by a person. Letters from any
    language, including accented ones, are left alone."""
    text = text or ''
    for ch in _INVISIBLE:
        text = text.replace(ch, '')
    for ch in _SPACES:
        text = text.replace(ch, ' ')
    for k, v in _QUOTES.items():
        text = text.replace(k, v)
    for k, v in _REPLACEMENTS.items():
        text = text.replace(k, v)
    for ch in _ARROWS:
        text = text.replace(ch, '->')
    # a bullet symbol at the start of a line is a list item; inside a line it is a separator
    text = re.sub(r'^[ \t]*[' + re.escape(_BULLET_SYMBOLS) + r'][ 	]*', '- ', text, flags=re.M)
    text = re.sub(r'[ 	]*[' + re.escape(_BULLET_SYMBOLS) + r'][ 	]*', ' | ', text)
    # en dash between numbers is a range (2022-2024); any other long dash is a pause, so use a comma
    text = re.sub(r'(?<=\d)\s*[–—―]\s*(?=\d)', '-', text)
    text = re.sub(r'\s*[—―]\s*', ', ', text)
    text = re.sub(r'\s+–\s+', ', ', text)
    text = text.replace('–', '-')
    text = _EMOJI.sub('', text)
    text = re.sub(r'[ \t]+,', ',', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'[ \t]+$', '', text, flags=re.M)
    return text


def clean_reply(text):
    """The model is told to answer in plain text; strip any markdown that slips through anyway."""
    text = _MARKDOWN_JUNK.sub('', text or '')
    text = _HEADING.sub('', text)
    text = re.sub(r'^\s*\*\s+', '- ', text, flags=re.M)
    return plain_text(text).strip()
