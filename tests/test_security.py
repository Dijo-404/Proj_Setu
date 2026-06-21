from app.security import create_session_token, hash_password, read_session_token, verify_password


def test_password_hash_roundtrip():
    password_hash = hash_password("secret")
    assert verify_password("secret", password_hash)
    assert not verify_password("wrong", password_hash)


def test_session_token_roundtrip():
    token = create_session_token(42)
    assert read_session_token(token) == 42
    assert read_session_token(token + "x") is None
