from enum import Enum

class ParseMode(str, Enum):
    HTML = "HTML"
    MARKDOWN = "Markdown"
    MARKDOWN_V2 = "MarkdownV2"

class GharanaType(int, Enum):
    SURYA = 1
    CHANDRA = 2
    AGNI = 3
    VAYU = 4
