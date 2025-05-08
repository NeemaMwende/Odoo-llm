from odoo import fields, models


class LLMGenerationConfig(models.Model):
    _name = "llm.generation.config"
    _description = "LLM Generation Configuration"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True, tracking=True)
    model_id = fields.Many2one(
        "llm.model", 
        string="Model", 
        ondelete="cascade", 
        tracking=True,
        help="The LLM model this configuration is for"
    )
    
    # Schema definitions
    input_schema = fields.Text(
        string="Input Schema",
        help="JSON Schema defining the input parameters for this generation task",
        tracking=True,
    )
    output_schema_raw = fields.Text(
        string="Raw Output Schema",
        help="Raw schema from the provider defining the output format",
        tracking=True,
    )
    
    # Metadata
    description = fields.Text(
        string="Description",
        help="Detailed description of what this generation configuration does",
        tracking=True,
    )
    active = fields.Boolean(default=True, tracking=True)
    
    _sql_constraints = [
        ('name_model_uniq', 'unique(name, model_id)', 'Generation configuration name must be unique per model!')
    ]
