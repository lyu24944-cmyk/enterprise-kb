from dataclasses import dataclass, field


@dataclass
class ParsedBlock:
    text: str
    page: int | None = None
    section: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    blocks: list[ParsedBlock]
    doc_type: str
    category: str = "other"
