"""TACT downloaderで扱う分類済み例外。"""


class TACTError(Exception):
    """TACT downloaderの共通基底例外。"""


class AuthenticationError(TACTError):
    """認証またはセッションに関する失敗。"""


class NetworkError(TACTError):
    """通信またはHTTP応答に関する失敗。"""


class DataError(TACTError, ValueError, OSError):
    """TACT APIの応答データが不正な場合の失敗。"""
