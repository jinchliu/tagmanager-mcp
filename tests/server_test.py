"""Checks that importing the server registers all expected tools."""

import asyncio
import unittest

from tagmanager_mcp import server

_READ_ONLY_TOOLS = {
    'list_accounts',
    'list_containers',
    'list_workspaces',
    'get_workspace_status',
    'list_tags',
    'get_tag',
    'list_triggers',
    'get_trigger',
    'list_variables',
    'get_variable',
}
_WRITE_TOOLS = {
    'create_tag',
    'update_tag',
    'create_trigger',
    'update_trigger',
    'create_variable',
    'update_variable',
}
_DESTRUCTIVE_TOOLS = {
    'delete_tag',
    'delete_trigger',
    'delete_variable',
}


class ToolRegistrationTest(unittest.TestCase):
    def test_all_tools_registered(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            _READ_ONLY_TOOLS | _WRITE_TOOLS | _DESTRUCTIVE_TOOLS,
        )

    def test_annotations_match_tool_class(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        for tool in tools:
            with self.subTest(tool=tool.name):
                self.assertIsNotNone(
                    tool.annotations, msg=f'{tool.name} lacks annotations'
                )
                if tool.name in _READ_ONLY_TOOLS:
                    self.assertTrue(tool.annotations.readOnlyHint)
                elif tool.name in _WRITE_TOOLS:
                    self.assertFalse(tool.annotations.readOnlyHint)
                    self.assertFalse(tool.annotations.destructiveHint)
                else:
                    self.assertFalse(tool.annotations.readOnlyHint)
                    self.assertTrue(tool.annotations.destructiveHint)

    def test_delete_tools_take_confirm_flag(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        for tool in tools:
            if tool.name in _DESTRUCTIVE_TOOLS:
                with self.subTest(tool=tool.name):
                    self.assertIn(
                        'confirm', tool.inputSchema.get('properties', {})
                    )


if __name__ == '__main__':
    unittest.main()
