#!/usr/bin/env python3
"""
RasoSpeak CLI — Headless command-line interface for your Second Brain.

Usage:
    python cli.py memory add "My first memory"
    python cli.py memory search "what did I learn"
    python cli.py memory stats
    python cli.py brain recall "project ideas"
    python cli.py brain export --format markdown
    python cli.py brain persona show
    python cli.py brain persona update name "Alice"
    python cli.py brain backup
    python cli.py brain patterns

Run from the RasoSpeak project root.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.second_brain_agent import SecondBrainAgent
from config.settings import settings


class MemoryCLI:
    """Headless CLI for Second Brain operations."""

    def __init__(self):
        self.brain = SecondBrainAgent()

    async def initialize(self):
        await self.brain.initialize()
        print("🧠 Connected to Second Brain")

    async def memory_add(self, content: str, memory_type: str = "general",
                         tier: str = "long_term", importance: int = 3,
                         tags: list = None):
        """Add a memory."""
        result = await self.brain.store(
            content=content,
            memory_type=memory_type,
            tier=tier,
            importance=importance,
            tags=tags or [],
        )
        print(f"✅ Memory stored: {result.get('node_id', 'unknown')}")
        return result

    async def memory_search(self, query: str, limit: int = 10):
        """Search memories."""
        result = await self.brain.recall(query=query, limit=limit)
        results = result.get("results", [])
        print(f"\n🔍 Search: \"{query}\" ({len(results)} results)\n")
        for i, r in enumerate(results, 1):
            content = r.get("content", "")[:120]
            mtype = r.get("memory_type", "unknown")
            relevance = r.get("relevance", 0)
            print(f"  {i}. [{mtype}] {relevance:.2f} — {content}")
        return results

    async def memory_stats(self):
        """Show memory statistics."""
        stats = await self.brain.get_stats()
        print("\n📊 Second Brain Stats")
        print(f"   Total memories:  {stats.get('total_memories', 0)}")
        print(f"   Quality score:   {stats.get('quality_score', 0)}%")
        print(f"   Conversations:   {stats.get('conversations', 0)}")
        print(f"   Semantic:        {stats.get('semantic', 0)}")
        print(f"   Episodes:        {stats.get('episodes', 0)}")
        print(f"   Documents:       {stats.get('documents', 0)}")
        print(f"   Audio:           {stats.get('audio', 0)}")
        print(f"   Goals:           {stats.get('goals', 0)}")
        print(f"   Auto-links:      {stats.get('auto_links', 0)}")
        print(f"   Compression:     {stats.get('compression_savings', 0)}%")
        return stats

    async def memory_list(self, limit: int = 20, tier: str = None):
        """List all memories."""
        all_nodes = list(self.brain._nodes.values())
        if tier:
            all_nodes = [n for n in all_nodes if n.tier.value == tier]
        all_nodes.sort(key=lambda n: n.created_at, reverse=True)
        print(f"\n📝 Recent Memories (showing {min(limit, len(all_nodes))} of {len(all_nodes)})\n")
        for n in all_nodes[:limit]:
            content = n.content[:80]
            print(f"   [{n.type.value}] {n.tier.value} — {content}")
        return all_nodes

    async def memory_forget(self, node_id: str):
        """Delete a memory."""
        self.brain._nodes.pop(node_id, None)
        self.brain._entity_index.pop(node_id, None)
        await self.brain._save_index()
        print(f"🗑️  Memory deleted: {node_id}")

    async def brain_recall(self, query: str, limit: int = 10):
        """Recall with full context."""
        result = await self.brain.recall(query=query, limit=limit)
        results = result.get("results", [])
        print(f"\n🧠 Recall: \"{query}\"\n")
        for i, r in enumerate(results, 1):
            content = r.get("content", "")
            mtype = r.get("memory_type", "unknown")
            relevance = r.get("relevance", 0)
            print(f"  {i}. [{mtype}] (relevance: {relevance:.2f})")
            print(f"     {content[:200]}")
            print()
        return results

    async def brain_export(self, format: str = "json"):
        """Export all memory."""
        export_data = await self.brain.export_memory(format_type=format)
        if format == "json":
            print(json.dumps(export_data, indent=2))
        elif format == "markdown":
            for section, content in export_data.get("markdown_sections", {}).items():
                print(f"## {section}\n{content}\n")
        return export_data

    async def brain_backup(self):
        """Create a backup."""
        backup = await self.brain.create_backup()
        print(f"\n💾 Backup created: {backup.get('backup_id')}")
        print(f"   Nodes backed up: {backup.get('node_count')}")
        print(f"   Compressed: {backup.get('compressed_kb')} KB")
        return backup

    async def brain_patterns(self):
        """Show detected memory patterns."""
        patterns = await self.brain.get_patterns()
        print("\n🔄 Detected Patterns\n")
        for p in patterns:
            print(f"  [{p.get('confidence', 0):.0%}] {p.get('pattern_type', 'unknown')}")
            print(f"    {p.get('description', '')}")
            print()
        return patterns

    async def brain_persona_show(self):
        """Show user persona."""
        persona = self.brain.get_persona()
        print("\n👤 User Persona\n")
        for key, value in persona.items():
            print(f"   {key}: {value}")
        return persona

    async def brain_persona_update(self, field: str, value: str):
        """Update persona field."""
        await self.brain.update_persona_field(field, value)
        print(f"✅ Persona updated: {field} = {value}")

    async def brain_goals(self):
        """Show all goals."""
        goals = await self.brain.get_all_goals()
        print(f"\n🎯 Goals ({len(goals)} total)\n")
        for g in goals:
            status = "✅" if g.get("completed") else "⏳"
            print(f"  {status} {g.get('title', 'Untitled')}")
            print(f"     Priority: {g.get('priority', 'medium')} | Progress: {g.get('progress', 0)}%")
            print(f"     Deadline: {g.get('deadline', 'none')}")
            print()
        return goals

    async def brain_goal_add(self, title: str, priority: str = "medium",
                            deadline: str = None, category: str = "general"):
        """Add a goal."""
        result = await self.brain.add_goal(
            title=title,
            priority=priority,
            deadline=deadline,
            category=category,
        )
        print(f"✅ Goal added: {result.get('goal_id')}")
        return result

    async def shutdown(self):
        await self.brain.shutdown()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="rasospeak",
        description="RasoSpeak CLI — Your Second Brain on the command line",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s memory add "Finished reading AI paper" --type conversation --tier long_term
  %(prog)s memory search "machine learning"
  %(prog)s memory stats
  %(prog)s memory list --limit 50 --tier long_term
  %(prog)s brain recall "what did I work on last week"
  %(prog)s brain export --format markdown
  %(prog)s brain backup
  %(prog)s brain patterns
  %(prog)s brain persona show
  %(prog)s brain goals
  %(prog)s brain goal add "Learn Rust" --priority high --deadline 2026-06-01
        """,
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # memory subcommands
    mem = sub.add_parser("memory", help="Memory operations")
    mem_sub = mem.add_subparsers(dest="memory_cmd")

    add = mem_sub.add_parser("add", help="Add a memory")
    add.add_argument("content", help="Memory content")
    add.add_argument("--type", "-t", default="general", help="Memory type")
    add.add_argument("--tier", default="long_term", help="Memory tier")
    add.add_argument("--importance", "-i", type=int, default=3, help="Importance 1-5")
    add.add_argument("--tags", nargs="*", help="Tags")

    search = mem_sub.add_parser("search", help="Search memories")
    search.add_argument("query", help="Search query")
    search.add_argument("--limit", "-l", type=int, default=10)

    stats = mem_sub.add_parser("stats", help="Show memory statistics")
    list_p = mem_sub.add_parser("list", help="List memories")
    list_p.add_argument("--limit", "-l", type=int, default=20)
    list_p.add_argument("--tier", help="Filter by tier")

    forget = mem_sub.add_parser("forget", help="Delete a memory")
    forget.add_argument("node_id", help="Memory node ID")

    # brain subcommands
    brain = sub.add_parser("brain", help="Second Brain operations")
    brain_sub = brain.add_subparsers(dest="brain_cmd")

    recall = brain_sub.add_parser("recall", help="Recall memories with context")
    recall.add_argument("query", help="Recall query")
    recall.add_argument("--limit", "-l", type=int, default=10)

    export = brain_sub.add_parser("export", help="Export memory")
    export.add_argument("--format", "-f", choices=["json", "markdown", "obsidian"],
                        default="json", help="Export format")

    backup = brain_sub.add_parser("backup", help="Create a backup")

    patterns = brain_sub.add_parser("patterns", help="Show detected patterns")

    persona = brain_sub.add_parser("persona", help="Manage user persona")
    persona_sub = persona.add_subparsers(dest="persona_cmd")
    persona_show = persona_sub.add_parser("show", help="Show persona")
    persona_update = persona_sub.add_parser("update", help="Update persona field")
    persona_update.add_argument("field", help="Field name")
    persona_update.add_argument("value", help="New value")

    goals = brain_sub.add_parser("goals", help="Manage goals")
    goals_sub = goals.add_subparsers(dest="goals_cmd")
    goals_list = goals_sub.add_parser("list", help="List all goals")
    goals_add = goals_sub.add_parser("add", help="Add a goal")
    goals_add.add_argument("title", help="Goal title")
    goals_add.add_argument("--priority", "-p", default="medium")
    goals_add.add_argument("--deadline", "-d", default=None)
    goals_add.add_argument("--category", "-c", default="general")

    return parser


async def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    cli = MemoryCLI()
    await cli.initialize()

    try:
        # Memory subcommands
        if args.command == "memory":
            if args.memory_cmd == "add":
                await cli.memory_add(args.content, args.type, args.tier,
                                     args.importance, args.tags)
            elif args.memory_cmd == "search":
                await cli.memory_search(args.query, args.limit)
            elif args.memory_cmd == "stats":
                await cli.memory_stats()
            elif args.memory_cmd == "list":
                await cli.memory_list(args.limit, args.tier)
            elif args.memory_cmd == "forget":
                await cli.memory_forget(args.node_id)
            else:
                parser.print_help()

        # Brain subcommands
        elif args.command == "brain":
            if args.brain_cmd == "recall":
                await cli.brain_recall(args.query, args.limit)
            elif args.brain_cmd == "export":
                await cli.brain_export(args.format)
            elif args.brain_cmd == "backup":
                await cli.brain_backup()
            elif args.brain_cmd == "patterns":
                await cli.brain_patterns()
            elif args.brain_cmd == "persona":
                if args.persona_cmd == "show":
                    await cli.brain_persona_show()
                elif args.persona_cmd == "update":
                    await cli.brain_persona_update(args.field, args.value)
                else:
                    parser.print_help()
            elif args.brain_cmd == "goals":
                if args.goals_cmd == "list":
                    await cli.brain_goals()
                elif args.goals_cmd == "add":
                    await cli.brain_goal_add(args.title, args.priority,
                                             args.deadline, args.category)
                else:
                    await cli.brain_goals()
            else:
                parser.print_help()

        else:
            parser.print_help()

    finally:
        await cli.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
