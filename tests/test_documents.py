from app.documents import chunk_text, load_document


def test_chunking_covers_text_with_overlap() -> None:
    chunks = chunk_text("abcdefghij klmnopqrst uvwxyz", "report.txt", None, 12, 3)
    assert len(chunks) > 1
    assert "".join(chunk.text for chunk in chunks).replace(" ", "").find("abcdefghij") >= 0
    assert all(chunk.source == "report.txt" for chunk in chunks)


def test_unsupported_document_type_is_rejected() -> None:
    try:
        load_document("report.csv", b"content")
    except ValueError as error:
        assert "Only PDF" in str(error)
    else:
        raise AssertionError("Unsupported file types must be rejected.")
