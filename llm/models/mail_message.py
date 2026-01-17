import base64
import logging

from odoo import api, fields, models, tools

_logger = logging.getLogger(__name__)

IMAGE_MIMETYPES = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
)

# Magic bytes for image type detection
IMAGE_MAGIC_BYTES = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",  # RIFF....WEBP
}

PDF_MIMETYPES = ("application/pdf",)

TEXT_MIMETYPES = (
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "text/css",
    "text/javascript",
    "text/xml",
    "text/x-python",
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-python-code",
)

SUPPORTED_IMAGE_MIMETYPES = IMAGE_MIMETYPES


def _detect_image_mimetype(raw_bytes):
    """Detect the real image mimetype from magic bytes.

    Args:
        raw_bytes: The raw image bytes

    Returns:
        The detected mimetype or None if not recognized
    """
    for magic, mimetype in IMAGE_MAGIC_BYTES.items():
        if raw_bytes.startswith(magic):
            # Special check for WebP: must have WEBP after RIFF header
            if magic == b"RIFF" and len(raw_bytes) >= 12:
                if raw_bytes[8:12] != b"WEBP":
                    continue
            return mimetype
    return None


class MailMessage(models.Model):
    _inherit = "mail.message"

    LLM_XMLIDS = (
        "llm.mt_tool",
        "llm.mt_user",
        "llm.mt_assistant",
        "llm.mt_system",
    )

    llm_role = fields.Char(
        string="LLM Role",
        compute="_compute_llm_role",
        store=True,
        index=True,  # Add index for better query performance
        help="The LLM role for this message (user, assistant, tool, system)",
    )

    body_json = fields.Json(
        string="JSON Body",
        help="JSON data for tool messages and other structured content",
    )

    @api.depends("subtype_id")
    def _compute_llm_role(self):
        """Compute the LLM role for messages based on their subtype."""
        id_to_role, _ = self.get_llm_roles()

        for message in self:
            if message.subtype_id and message.subtype_id.id in id_to_role:
                message.llm_role = id_to_role[message.subtype_id.id]
            else:
                message.llm_role = False

    @tools.ormcache()
    def get_llm_roles(self):
        """Get cached mapping of LLM subtype IDs to clean role names and vice versa.

        Returns:
            tuple: (id_to_role_dict, role_to_id_dict) where:
                - id_to_role_dict: {subtype_id: 'user', subtype_id: 'assistant', ...}
                - role_to_id_dict: {'user': subtype_id, 'assistant': subtype_id, ...}
        """
        id_to_role = {}
        role_to_id = {}

        for xmlid in self.LLM_XMLIDS:
            subtype_id = self.env["ir.model.data"]._xmlid_to_res_id(
                xmlid,
                raise_if_not_found=False,
            )
            if subtype_id:
                # Extract clean role name (e.g., 'user' from 'llm.mt_user')
                role = xmlid.split(".")[-1][3:]  # Remove 'mt_' prefix
                id_to_role[subtype_id] = role
                role_to_id[role] = subtype_id

        return id_to_role, role_to_id

    def get_llm_role(self):
        """Get the LLM role for this message (ensure_one).

        DEPRECATED: Use the llm_role computed field instead.

        Returns:
            str or False: The role name ('user', 'assistant', 'tool', 'system') or False if not an LLM message
        """
        self.ensure_one()
        return self.llm_role

    def is_llm_message(self):
        """Check if messages are LLM messages using the stored field."""
        return {message: bool(message.llm_role) for message in self}

    def is_llm_user_message(self):
        """Check if messages are LLM user messages using the stored field."""
        return {message: message.llm_role == "user" for message in self}

    def is_llm_assistant_message(self):
        """Check if messages are LLM assistant messages using the stored field."""
        return {message: message.llm_role == "assistant" for message in self}

    def is_llm_tool_message(self):
        """Check if messages are LLM tool messages using the stored field."""
        return {message: message.llm_role == "tool" for message in self}

    def is_llm_system_message(self):
        """Check if messages are LLM system messages using the stored field."""
        return {message: message.llm_role == "system" for message in self}

    def _check_llm_role(self, role):
        """Check if messages match a specific LLM role using the stored field.

        Args:
            role (str): The role name ('user', 'assistant', 'tool', 'system')
        """
        return {message: message.llm_role == role for message in self}

    def to_store_format(self):
        """Convert message to store format compatible with Odoo 18.0. Used by frontend js components"""
        self.ensure_one()
        from odoo.addons.mail.tools.discuss import Store

        store = Store()
        self._to_store(store)
        result = store.get_result()

        return result["mail.message"][0]

    def _get_image_attachments(self):
        """Get image attachments with validated mimetype from magic bytes.

        Returns list of dicts with mimetype (validated), data (base64), and name.
        The mimetype is detected from the actual image content, not from Odoo's
        stored mimetype, to ensure compatibility with strict API validators
        like Anthropic Claude.
        """
        self.ensure_one()
        images = []
        for att in self.attachment_ids:
            if att.mimetype and att.mimetype in SUPPORTED_IMAGE_MIMETYPES:
                if att.datas:
                    # Decode base64 to get raw bytes for magic byte detection
                    try:
                        raw_bytes = base64.b64decode(att.datas)
                        real_mimetype = _detect_image_mimetype(raw_bytes)

                        if real_mimetype:
                            # Use detected mimetype instead of stored one
                            if real_mimetype != att.mimetype:
                                _logger.debug(
                                    "Image %s: correcting mimetype from %s to %s",
                                    att.name,
                                    att.mimetype,
                                    real_mimetype,
                                )
                            images.append(
                                {
                                    "mimetype": real_mimetype,
                                    "data": att.datas.decode("utf-8"),
                                    "name": att.name or "image",
                                },
                            )
                        else:
                            # Fallback to stored mimetype if detection fails
                            _logger.warning(
                                "Could not detect image type for %s, using stored mimetype %s",
                                att.name,
                                att.mimetype,
                            )
                            images.append(
                                {
                                    "mimetype": att.mimetype,
                                    "data": att.datas.decode("utf-8"),
                                    "name": att.name or "image",
                                },
                            )
                    except (ValueError, TypeError) as e:
                        _logger.warning(
                            "Failed to process image attachment %s: %s",
                            att.name,
                            e,
                        )
        return images

    def _get_pdf_attachments(self):
        self.ensure_one()
        pdfs = []
        for att in self.attachment_ids:
            if att.mimetype and att.mimetype in PDF_MIMETYPES:
                if att.datas:
                    pdfs.append(
                        {
                            "mimetype": att.mimetype,
                            "data": att.datas.decode("utf-8"),
                            "name": att.name or "document.pdf",
                        },
                    )
        return pdfs

    def _get_text_attachments(self):
        self.ensure_one()
        texts = []
        for att in self.attachment_ids:
            if att.mimetype and att.mimetype in TEXT_MIMETYPES:
                if att.datas:
                    try:
                        raw_data = base64.b64decode(att.datas)
                        content = raw_data.decode("utf-8")
                        texts.append(
                            {
                                "mimetype": att.mimetype,
                                "content": content,
                                "name": att.name or "file.txt",
                            },
                        )
                    except (UnicodeDecodeError, ValueError) as e:
                        _logger.warning(
                            "Failed to decode text attachment %s: %s",
                            att.name,
                            e,
                        )
        return texts
