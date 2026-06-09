import re
from dataclasses import dataclass, field

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


def extract_year(site_id: str, raw_title: str) -> str:
    """サイトIDまたはタイトルから年度を抽出する。"""
    # site_id の先頭4桁を年度として使用 (例: 2025_XXXXX)
    match = re.match(r"(\d{4})_", site_id)
    if match:
        year = int(match.group(1))
        return f"{year}年度"

    # タイトルから年度を抽出 (例: 2025年度, 2025春学期)
    match = re.search(r"(\d{4})\s*年度?", raw_title)
    if match:
        year = int(match.group(1))
        return f"{year}年度"

    # 西暦4桁を探す
    match = re.search(r"(20\d{2})", raw_title)
    if match:
        year = int(match.group(1))
        return f"{year}年度"

    return "未分類"


def extract_semester(raw_title: str) -> str:
    """タイトルから学期情報を抽出する。見つからない場合は空文字列。"""
    # 【春1期】のような括弧で囲まれた学期表記を優先
    bracket_match = re.search(r"[\[［【]([^\]］】]*期[^\]］】]*)[\]］】]", raw_title)
    if bracket_match:
        return bracket_match.group(1)

    bracket_match = re.search(r"[\[［【]([^\]］】]*学期[^\]］】]*)[\]］】]", raw_title)
    if bracket_match:
        return bracket_match.group(1)

    # 【春A】のようなターム/クォーター表記
    bracket_match = re.search(r"[\[［【]([^\]］】]*[AB][^\]］】]*)[\]］】]", raw_title)
    if bracket_match:
        return bracket_match.group(1)

    bracket_match = re.search(r"[\[［【]([^\]］】]*ターム[^\]］】]*)[\]］】]", raw_title)
    if bracket_match:
        return bracket_match.group(1)

    # 括弧なしでマッチ
    for pattern, label in SEMESTER_PATTERNS:
        if re.search(pattern, raw_title):
            return label

    return ""


def extract_course_name(raw_title: str, semester: str) -> str:
    """タイトルから学期表記と年度表記を除去して授業名を抽出する。"""
    name = raw_title

    # 括弧で囲まれた学期表記を除去
    name = re.sub(r"[\[［【][^\]］】]*(?:期|学期|ターム|[AB])[^\]］】]*[\]］】]\s*", "", name)

    # 年度表記を除去 (例: "2025", "2025年度", "2025年")
    name = re.sub(r"\d{4}\s*(?:年度|年)?\s*[_\s\-]*", "", name)

    # 残った学期・期・ターム・クォーター表記を除去
    for pattern, _ in SEMESTER_PATTERNS:
        name = re.sub(pattern + r"\s*[_\s\-]*", "", name)

    # 先頭と末尾の空白・記号を除去
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
