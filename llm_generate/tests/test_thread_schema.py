from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestThreadSchema(TransactionCase):
    """Test thread schema handling and form configuration"""

    def setUp(self):
        super().setUp()
        self.thread_model = self.env["llm.thread"]
        self.prompt_model = self.env["llm.prompt"]
        self.provider_model = self.env["llm.provider"]
        self.model_model = self.env["llm.model"]

        # Create a test provider
        self.test_provider = self.provider_model.create(
            {
                "name": "Test Provider",
                "service": "test",
            }
        )

        # Create a test model with input schema already populated
        # Use "text" model_use to avoid triggering auto-generation
        # (schema generation is tested in provider-specific modules)
        self.test_model = self.model_model.create(
            {
                "name": "test-model",
                "provider_id": self.test_provider.id,
                "model_use": "text",
                "details": {
                    "input_schema": {
                        "type": "object",
                        "properties": {"model_field": {"type": "string"}},
                    }
                },
            }
        )

        # Create a test prompt with schema
        self.test_prompt = self.prompt_model.create(
            {
                "name": "Test Schema Prompt",
                "template": "Hello {{name}}, you are {{age}} years old.",
                "format": "text",
                "input_schema_json": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"},
                    },
                },
            }
        )

    def test_get_input_schema_priority_order(self):
        """Test that schema is retrieved from model when no assistant/prompt"""
        # Use new() to create in-memory records without database constraints
        thread = self.thread_model.new({"name": "Test Thread"})
        thread.model_id = self.test_model

        # Test: No assistant, should return model schema
        schema = thread.get_input_schema()
        self.assertEqual(schema["properties"]["model_field"]["type"], "string")

    def test_get_form_defaults_with_schema(self):
        """Test that form defaults include context values"""
        thread = self.thread_model.new({"name": "Test Thread"})

        # Mock get_context at the class level instead of instance level
        with patch.object(
            type(thread), "get_context", return_value={"name": "John"}
        ):
            defaults = thread.get_form_defaults()

            # Should include context value
            self.assertEqual(defaults.get("name"), "John")

    def test_ensure_dict_conversion(self):
        """Test the _ensure_dict helper method"""
        thread = self.thread_model.new()

        # Test with dict input
        result = thread._ensure_dict({"key": "value"})
        self.assertEqual(result, {"key": "value"})

        # Test with JSON string input
        result = thread._ensure_dict('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

        # Test with invalid JSON string
        result = thread._ensure_dict("invalid json")
        self.assertEqual(result, {})

        # Test with None/other types
        result = thread._ensure_dict(None)
        self.assertEqual(result, {})


    def test_prepare_generation_inputs_without_prompt(self):
        """Test input preparation without prompt (direct passthrough)"""
        thread = self.thread_model.new({"name": "Test Thread"})
        # No prompt_id set

        # Mock get_context at class level
        with patch.object(
            type(thread), "get_context", return_value={"context_var": "value"}
        ):
            inputs = {"user_input": "test"}

            result = thread.prepare_generation_inputs(inputs)

            # Should return merged context + inputs
            self.assertEqual(result["context_var"], "value")
            self.assertEqual(result["user_input"], "test")

