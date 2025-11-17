import base64
import logging

from odoo import models
from odoo.addons.llm_tool.decorators import llm_tool
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @llm_tool(
        name="llm_mistral_attachment_parser",
        description="Extract text and structured data from a PDF or image attachment using Mistral OCR vision model",
    )
    def llm_mistral_attachment_parser(self, attachment_id):
        """
        Parse a document attachment using Mistral OCR.

        This tool extracts text content from PDF files and images using Mistral's
        OCR (Optical Character Recognition) vision models. The result is formatted
        as markdown text with page headers.

        Args:
            attachment_id (int): ID of the attachment to parse

        Returns:
            dict: {
                "extracted_text": str,  # Markdown-formatted text content
                "pages": int,           # Number of pages processed
                "attachment_name": str, # Original filename
                "mimetype": str,        # File type
            }

        Raises:
            ValidationError: If attachment not found or has no content
            UserError: If Mistral provider or OCR model not configured

        Example:
            >>> self.env['ir.attachment'].llm_mistral_attachment_parser(attachment_id=123)
            {
                "extracted_text": "## Page 1\n\nInvoice #12345...",
                "pages": 2,
                "attachment_name": "invoice.pdf",
                "mimetype": "application/pdf"
            }
        """
        # Get the attachment
        attachment = self.browse(attachment_id)
        if not attachment.exists():
            raise ValidationError(f"Attachment with ID {attachment_id} not found")

        # Get provider
        provider = self.env["llm.provider"].search(
            [("service", "=", "mistral")], limit=1
        )
        if not provider:
            raise UserError(
                "Mistral provider not found. Please configure Mistral AI provider in LLM settings."
            )

        # Find OCR model with priority:
        # 1. mistral-ocr-latest with model_use = ocr
        # 2. Any model named mistral-ocr-latest
        # 3. Any model with model_use = ocr
        ocr_model = self.env["llm.model"].search(
            [
                ("provider_id", "=", provider.id),
                ("name", "=", "mistral-ocr-latest"),
                ("model_use", "=", "ocr"),
            ],
            limit=1,
        )

        if not ocr_model:
            # Fallback: Any model named mistral-ocr-latest
            ocr_model = self.env["llm.model"].search(
                [
                    ("provider_id", "=", provider.id),
                    ("name", "=", "mistral-ocr-latest"),
                ],
                limit=1,
            )

        if not ocr_model:
            # Fallback: Any OCR model
            ocr_model = self.env["llm.model"].search(
                [
                    ("provider_id", "=", provider.id),
                    ("model_use", "=", "ocr"),
                ],
                limit=1,
            )

        if not ocr_model:
            raise UserError(
                "No OCR model found. Please sync models from Mistral provider settings."
            )

        # Get attachment data
        mimetype = attachment.mimetype or "application/pdf"
        datas = attachment.datas

        if not datas:
            raise ValidationError(f"Attachment '{attachment.name}' has no content")

        # Decode base64 to bytes
        data_bytes = base64.b64decode(datas)

        # Call provider's OCR processing
        ocr_response = provider.process_ocr(
            model_name=ocr_model.name,
            data=data_bytes,
            mimetype=mimetype,
        )

        # Format response to markdown
        extracted_text = self._format_ocr_response(ocr_response)

        return {
            "extracted_text": extracted_text,
            "pages": len(ocr_response.pages) if hasattr(ocr_response, "pages") else 1,
            "attachment_name": attachment.name,
            "mimetype": mimetype,
        }

    def _format_ocr_response(self, ocr_response):
        """
        Format Mistral OCR response into simple markdown text.

        Args:
            ocr_response: Response object from Mistral OCR API

        Returns:
            str: Markdown-formatted text with page headers
        """
        parts = []

        for page_idx, page in enumerate(ocr_response.pages, start=1):
            page_md = page.markdown.strip() if page.markdown else ""
            if page_md:
                parts.append(f"## Page {page_idx}\n\n{page_md}")

        return "\n\n".join(parts) if parts else ""
