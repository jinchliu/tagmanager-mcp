"""Checks that importing the server registers all expected tools."""

import asyncio
import unittest

from tagmanager_mcp import server

_EXPECTED_TOOLS = {
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


class ToolRegistrationTest(unittest.TestCase):
    def test_all_read_only_tools_registered(self) -> None:
        tools = asyncio.run(server.mcp.list_tools())
        self.assertEqual({tool.name for tool in tools}, _EXPECTED_TOOLS)
        for tool in tools:
            self.assertIsNotNone(
                tool.annotations, msg=f'{tool.name} lacks annotations'
            )
            self.assertTrue(
                tool.annotations.readOnlyHint,
                msg=f'{tool.name} must declare readOnlyHint',
            )


if __name__ == '__main__':
    unittest.main()
