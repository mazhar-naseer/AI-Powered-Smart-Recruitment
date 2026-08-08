"""Throwaway diagnostic: upload a raw PDF and try every retrieval strategy.

Run from backend/ with the real credentials in ../.env. Delete when done.
"""

import sys
import uuid
from io import BytesIO
from urllib.error import HTTPError
from urllib.request import urlopen

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils

from app.config import get_settings

settings = get_settings()
cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)
print(f"cloud={settings.cloudinary_cloud_name} sdk={cloudinary.VERSION}")

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
public_id = f"smarthire/probe/{uuid.uuid4().hex}.pdf"

print("\n[1] upload raw/authenticated")
try:
    result = cloudinary.uploader.upload(
        BytesIO(PDF), public_id=public_id, resource_type="raw",
        type="authenticated", overwrite=False,
    )
    print(f"    OK public_id={result['public_id']} bytes={result.get('bytes')}")
except Exception as exc:
    print(f"    FAIL {type(exc).__name__}: {exc}")
    sys.exit(1)


def attempt(label, url):
    try:
        with urlopen(url, timeout=30) as response:
            body = response.read()
        print(f"    {label}: OK {len(body)} bytes, matches={body == PDF}")
        return True
    except HTTPError as exc:
        print(f"    {label}: HTTP {exc.code} {exc.reason}")
    except Exception as exc:
        print(f"    {label}: {type(exc).__name__}: {exc}")
    return False


print("\n[2] signed delivery URL (what the code does today)")
url, _ = cloudinary.utils.cloudinary_url(
    public_id, resource_type="raw", type="authenticated", sign_url=True, secure=True
)
print(f"    {url}")
attempt("delivery", url)

print("\n[3] signed delivery URL with long_url_signature")
url_long, _ = cloudinary.utils.cloudinary_url(
    public_id, resource_type="raw", type="authenticated", sign_url=True,
    secure=True, long_url_signature=True,
)
attempt("delivery-long", url_long)

print("\n[4] private_download_url (API download endpoint, not the CDN)")
try:
    dl = cloudinary.utils.private_download_url(
        public_id, None, resource_type="raw", type="authenticated"
    )
    print(f"    {dl.split('?')[0]}?<signed>")
    attempt("download-api", dl)
except Exception as exc:
    print(f"    FAIL {type(exc).__name__}: {exc}")

print("\n[5] admin api resource metadata")
try:
    info = cloudinary.api.resource(public_id, resource_type="raw", type="authenticated")
    print(f"    OK format={info.get('format')} bytes={info.get('bytes')}")
    attempt("secure_url-direct", info["secure_url"])
except Exception as exc:
    print(f"    FAIL {type(exc).__name__}: {exc}")

print("\n[6] cleanup")
try:
    cloudinary.uploader.destroy(public_id, resource_type="raw", type="authenticated")
    print("    destroyed")
except Exception as exc:
    print(f"    FAIL {type(exc).__name__}: {exc}")
