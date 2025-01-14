"Document signature generation"
import hashlib
from datetime import timezone
from unittest.mock import patch

from .syntax import build_obj_dict
from .syntax import create_dictionary_string


class Signature:
    def __init__(self, contact_info=None, location=None, m=None, reason=None):
        self.type = "/Sig"
        self.filter = "/Adobe.PPKLite"
        self.sub_filter = "/adbe.pkcs7.detached"
        self.contact_info = contact_info
        "Information provided by the signer to enable a recipient to contact the signer to verify the signature"
        self.location = location
        "The CPU host name or physical location of the signing"
        self.m = m
        "The time of signing"
        self.reason = reason
        "The reason for the signing"
        self.byte_range = _SIGNATURE_BYTERANGE_PLACEHOLDER
        self.contents = "<" + _SIGNATURE_CONTENTS_PLACEHOLDER + ">"

    def serialize(self):
        obj_dict = build_obj_dict({key: getattr(self, key) for key in dir(self)})
        return create_dictionary_string(obj_dict)


def sign_content(signer, buffer, key, cert, extra_certs, hashalgo, sign_time):
    """
    Perform PDF signing based on the content of the buffer, performing substitutions on it.
    The signing operation does not alter the buffer size
    """
    # We start by substituting the ByteRange,
    # that defines which part of the document content the signature is based on.
    # This is basically ALL the content EXCEPT the signature content itself.
    sig_placeholder = _SIGNATURE_CONTENTS_PLACEHOLDER.encode("latin1")
    start_index = buffer.find(sig_placeholder)
    end_index = start_index + len(sig_placeholder)
    content_range = (0, start_index - 1, end_index + 1, len(buffer) - end_index - 1)
    br_placeholder = _SIGNATURE_BYTERANGE_PLACEHOLDER.encode()
    byte_range = b"[%010d %010d %010d %010d]" % content_range
    # Sanity check, otherwise we will break the xref table:
    assert len(br_placeholder) == len(byte_range)
    buffer = buffer.replace(br_placeholder, byte_range, 1)

    # We compute the ByteRange hash, of everything before & after the placeholder:
    content_hash = hashlib.new(hashalgo)
    content_hash.update(buffer[: content_range[1]])  # before
    content_hash.update(buffer[content_range[2] :])  # after

    # This monkey-patching is needed, at the time of endesive v2.0.9,
    # to get control over signed_time, initialized by endesive.signer.sign() to be datetime.now():
    class mock_datetime:
        @staticmethod
        def now(tz):  # pylint: disable=unused-argument
            return sign_time.astimezone(timezone.utc)

    sign = patch("endesive.signer.datetime", mock_datetime)(signer.sign)

    contents = sign(
        datau=None,
        key=key,
        cert=cert,
        othercerts=extra_certs,
        hashalgo=hashalgo,
        attrs=True,
        signed_value=content_hash.digest(),
    )
    contents = _pkcs11_aligned(contents).encode("latin1")
    # Sanity check, otherwise we will break the xref table:
    assert len(sig_placeholder) == len(contents)
    return buffer.replace(sig_placeholder, contents, 1)


def _pkcs11_aligned(data):
    data = "".join(f"{i:02x}" for i in data)
    return data + "0" * (0x4000 - len(data))


_SIGNATURE_BYTERANGE_PLACEHOLDER = "[0000000000 0000000000 0000000000 0000000000]"
_SIGNATURE_CONTENTS_PLACEHOLDER = _pkcs11_aligned((0,))
