from app.email_service import build_verification_message
from app.models import Role, User


def test_verification_email_is_multipart_branded_and_escapes_user_content():
    user = User(
        email="candidate@example.com",
        full_name="Candidate <script>",
        password_hash="unused",
        role=Role.APPLICANT,
    )
    message = build_verification_message(
        user, "482913", "http://localhost:5173/verify-email?token=safe-token"
    )
    plain = message.get_body(preferencelist=("plain",)).get_content()
    html = message.get_body(preferencelist=("html",)).get_content()
    assert message.is_multipart()
    assert "482913" in message["Subject"]
    assert "Verification code: 482913" in plain
    assert "Verify my account" in html
    assert "SmartHire" in html
    assert "Candidate &lt;script&gt;" in html
    assert "Candidate <script>" not in html
