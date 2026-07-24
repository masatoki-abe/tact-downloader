import re
from dataclasses import dataclass

SEMESTER_PATTERNS: list[tuple[str, str]] = [
    # 学期n期形式（優先度高）
    (r"春1期", "春1期"),
    (r"春2期", "春2期"),
    (r"秋1期", "秋1期"),
    (r"秋2期", "秋2期"),
    (r"春3期", "春3期"),
    (r"秋3期", "秋3期"),
    # 学期形式
    (r"春学期", "春学期"),
    (r"秋学期", "秋学期"),
    (r"前期", "前期"),
    (r"後期", "後期"),
    (r"通年", "通年"),
    # ターム形式（一部大学で使用）
    (r"第1ターム", "第1ターム"),
    (r"第2ターム", "第2ターム"),
    (r"第3ターム", "第3ターム"),
    (r"第4ターム", "第4ターム"),
    # クォーター形式
    (r"春A", "春A"),
    (r"春B", "春B"),
    (r"秋A", "秋A"),
    (r"秋B", "秋B"),
    # 集中・通年
    (r"集中", "集中"),
    (r"特別", "特別"),
]


@dataclass
class SiteInfo:
    site_id: str
    raw_title: str
    year: str
    semester: str
    course_name: str


def _normalize_text(text: str) -> str:
    """全角英数字を半角に変換する。"""
    result: list[str] = []
    for c in text:
        code = ord(c)
        if 0xFF10 <= code <= 0xFF19:
            result.append(chr(code - 0xFEE0))
        elif 0xFF21 <= code <= 0xFF3A:
            result.append(chr(code - 0xFEE0))
        elif 0xFF41 <= code <= 0xFF5A:
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            result.append(" ")
        else:
            result.append(c)
    return "".join(result)


def extract_year(site_id: str, raw_title: str) -> str:
    """サイトIDまたはタイトルから年度を抽出する。"""
    title = _normalize_text(raw_title)

    # タイトルから年度を抽出（最後のマッチを優先: "（2022年度以降入学者）" のような
    # 講義名内の年度表記を避け、末尾の "(YYYY年度学期/時限)" の年度を採用する）
    matches = list(re.finditer(r"(\d{4})\s*年度?", title))
    if matches:
        year = int(matches[-1].group(1))
        return f"{year}年度"

    # タイトル内の西暦4桁を探す
    match = re.search(r"(20\d{2})", title)
    if match:
        year = int(match.group(1))
        return f"{year}年度"

    # site_id に含まれる4桁の数字を年度として使用 (例: n_2024_XXXXX)
    match = re.search(r"(\d{4})_", site_id)
    if match:
        year = int(match.group(1))
        return f"{year}年度"

    return "未分類"


def extract_semester(raw_title: str) -> str:
    """タイトルから学期情報を抽出する。見つからない場合は空文字列。"""
    title = _normalize_text(raw_title)

    # 【春1期】のようなタグ的括弧で囲まれた学期表記を優先する。
    for open_b, close_b in [("【", "】"), ("［", "］"), ("[", "]")]:
        pattern = rf"{re.escape(open_b)}([^{re.escape(close_b)}]*){re.escape(close_b)}"
        for bracket_match in re.finditer(pattern, title):
            label = _match_semester(bracket_match.group(1))
            if label:
                return label

    # 末尾の括弧ブロックから、既知の学期パターンだけを採用する。
    block_match = re.search(r"[（(]([^）)]*)[）)]\s*$", title)
    if block_match:
        block = block_match.group(1)
        block = re.sub(r"\d{4}\s*年度?", "", block).strip()
        return _match_semester(block) or ""

    return ""


def _match_semester(text: str) -> str:
    """文字列中の既知の学期パターンを正規化して返す。"""
    for pattern, label in SEMESTER_PATTERNS:
        if re.search(pattern, text):
            return label
    return ""


def extract_course_name(raw_title: str, semester: str) -> str:
    """タイトルから学期表記と年度表記を除去して授業名を抽出する。"""
    name = _normalize_text(raw_title)

    # 実際に認識した末尾の学期ブロックだけを除去する。
    if semester:
        name = re.sub(r"[（(][^）)]*[）)]\s*$", "", name)
    else:
        # 未確定の年度・時限ブロックは学期未検出でもメタデータとして除去する。
        name = re.sub(r"[（(][^）)]*/[^）)]*[）)]\s*$", "", name)

    # [遠隔] や 【l】 や （学部）のようなタグ的括弧を先頭から除去
    name = re.sub(r"^[\[（(［【][^\]）)］】]*[\]）)］】]\s*", "", name)

    # 先頭の年度表記のみ除去 (例: "2025年度 情報学部4年" → "情報学部4年")
    name = re.sub(r"^\d{4}\s*(?:年度|年)?\s*[_\s\-]*", "", name)

    # 残った孤立した括弧類を除去
    name = re.sub(r"^[\s_\-【\[［]+", "", name)
    name = re.sub(r"[\s_\-】\]］]+$", "", name)
    name = name.strip()

    return name or raw_title


def classify_site(site_id: str, raw_title: str) -> SiteInfo:
    """サイトIDとタイトルから SiteInfo を生成する。"""
    year = extract_year(site_id, raw_title)
    semester = extract_semester(raw_title)
    course_name = extract_course_name(raw_title, semester)
    return SiteInfo(
        site_id=site_id,
        raw_title=raw_title,
        year=year,
        semester=semester,
        course_name=course_name,
    )
