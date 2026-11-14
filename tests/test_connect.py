from urllib.parse import parse_qs, urlparse

from project_opener.core import connect
from project_opener.core import models as M


def project() -> M.Project:
    p = M.Project(name="As-built isometrics", job_number="P12513", client="Reliance", description="Area 3 piping")
    p.items = [M.Item(path="Z:/P12513/model.nwd", label="Model"), M.Item(path="x", enabled=False)]
    return p


def test_share_url_carries_the_project_and_its_link():
    p = project()
    url = connect.share_url(p, to="priya.raman")
    u = urlparse(url)
    assert u.scheme == "dexconnect" and u.netloc == "share"
    q = parse_qs(u.query)
    assert q["from"] == ["Project Opener"]
    assert q["to"] == ["priya.raman"]
    assert q["link"] == [f"projectopener://open/{p.id}"]
    assert q["title"] == ["Open in Project Opener"]
    text = q["text"][0]
    assert text.splitlines()[0] == "**P12513 · As-built isometrics**"
    assert "Client: Reliance" in text and "Area 3 piping" in text and "1 item to open" in text


def test_ids_and_text_are_encoded_safely():
    p = project()
    p.id = "a b/c"
    p.description = "Line 6\"-P-1001 & 2\"-P-1002?"
    url = connect.share_url(p)
    assert " " not in url
    q = parse_qs(urlparse(url).query)
    assert q["link"] == ["projectopener://open/a%20b%2Fc"]
    assert "& 2\"-P-1002?" in q["text"][0]


def test_share_does_nothing_without_connect(monkeypatch):
    monkeypatch.setattr(connect, "connect_installed", lambda: False)
    assert connect.share(project()) is False


def test_share_reports_failure_when_windows_cannot_start_connect(monkeypatch):
    def broken(_url: str) -> None:
        raise OSError("The system cannot find the file specified")

    monkeypatch.setattr(connect, "connect_installed", lambda: True)
    monkeypatch.setattr(connect.os, "startfile", broken, raising=False)
    assert connect.share(project()) is False


def test_share_hands_the_link_to_windows(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(connect, "connect_installed", lambda: True)
    monkeypatch.setattr(connect.os, "startfile", opened.append, raising=False)
    assert connect.share(project(), to="space:piping p-12513") is True
    assert len(opened) == 1 and opened[0].startswith("dexconnect://share?") and "to=space%3Apiping%20p-12513" in opened[0]
