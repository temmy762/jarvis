"""Trello intent router for natural language task management commands.

This module interprets user task management requests and routes to appropriate
Trello functions, returning clean, formatted responses for Saara.
"""

from typing import Any, Dict, Optional, List
import logging

from src.services.trello_advanced import (
    trello_list_boards,
    trello_list_lists,
    trello_list_cards,
    trello_get_board_cards,
    trello_create_card,
    trello_get_card,
    trello_update_card,
    trello_move_card,
    trello_delete_card,
    trello_search_cards,
    trello_create_board,
    trello_create_list,
    trello_find_board_by_name,
    trello_find_list_by_name,
    trello_find_card_by_name,
    trello_sort_cards_by_due_date,
    trello_group_cards_by_status,
    trello_group_cards_by_label,
    trello_filter_cards_by_due_date,
    _format_card_readable,
)


logger = logging.getLogger("jarvis.trello_intent")


def _format_board_list(boards: List[Dict[str, Any]]) -> str:
    """Format boards in clean plain text."""
    if not boards:
        return "You have no Trello boards."
    
    output = "Your Trello boards:\n\n"
    for i, board in enumerate(boards, 1):
        name = board.get("name", "Untitled")
        output += f"{i}. {name}\n"
    
    return output.strip()


def _format_list_list(lists: List[Dict[str, Any]]) -> str:
    """Format lists in clean plain text."""
    if not lists:
        return "This board has no lists."
    
    output = "Lists on this board:\n\n"
    for i, list_item in enumerate(lists, 1):
        name = list_item.get("name", "Untitled")
        output += f"{i}. {name}\n"
    
    return output.strip()


def _format_card_list(cards: List[Dict[str, Any]]) -> str:
    """Format cards in clean plain text."""
    if not cards:
        return "No tasks found."
    
    output = ""
    for i, card in enumerate(cards, 1):
        output += f"\n{i}. {_format_card_readable(card)}\n"
    
    return output.strip()


def _format_grouped_cards(grouped: Dict[str, List[Dict[str, Any]]]) -> str:
    """Format grouped cards in clean plain text."""
    output = ""
    
    for group_name, cards in grouped.items():
        output += f"\n{group_name}:\n"
        if not cards:
            output += "  No tasks\n"
        else:
            for card in cards:
                name = card.get("name", "Untitled")
                output += f"  - {name}\n"
    
    return output.strip()


async def handle_trello_intent(
    action: str,
    board_name: Optional[str] = None,
    board_id: Optional[str] = None,
    list_name: Optional[str] = None,
    list_id: Optional[str] = None,
    card_name: Optional[str] = None,
    card_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    due: Optional[str] = None,
    labels: Optional[List[str]] = None,
    members: Optional[List[str]] = None,
    fields: Optional[Dict[str, Any]] = None,
    keyword: Optional[str] = None,
    filter_type: Optional[str] = None,
    confirm_delete: bool = False,
) -> Dict[str, Any]:
    
    action = action.lower().strip()
    
    # List boards
    if action == "list_boards":
        result = await trello_list_boards()
        if not result.get("success"):
            return result
        
        boards = result["data"]
        message = _format_board_list(boards)
        
        return {
            "success": True,
            "message": message,
            "data": boards
        }
    
    # List lists on a board
    if action == "list_lists":
        if not board_id and not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which board should I check?"
            }
        
        if board_name and not board_id:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                return {
                    "success": False,
                    "error": "BOARD_NOT_FOUND",
                    "message": f"I couldn't find a board called '{board_name}'."
                }
            board_id = board_result["data"]["id"]
        
        result = await trello_list_lists(board_id)
        if not result.get("success"):
            return result
        
        lists = result["data"]
        message = _format_list_list(lists)
        
        return {
            "success": True,
            "message": message,
            "data": lists
        }
    
    # Get tasks on a board
    if action == "get_board_tasks":
        if not board_id and not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which board should I check?"
            }
        
        if board_name and not board_id:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                return {
                    "success": False,
                    "error": "BOARD_NOT_FOUND",
                    "message": f"I couldn't find a board called '{board_name}'."
                }
            board_id = board_result["data"]["id"]
        
        result = await trello_get_board_cards(board_id)
        if not result.get("success"):
            return result
        
        cards = result["data"]
        message = _format_card_list(cards)
        
        return {
            "success": True,
            "message": message,
            "data": cards
        }
    
    # Get tasks in a list
    if action == "get_list_tasks":
        if not list_id and not list_name:
            return {
                "success": False,
                "error": "MISSING_LIST",
                "message": "Which list should I check?"
            }
        
        if list_name and not list_id:
            if not board_id and not board_name:
                return {
                    "success": False,
                    "error": "MISSING_BOARD",
                    "message": "Which board is this list on?"
                }
            
            if board_name and not board_id:
                board_result = await trello_find_board_by_name(board_name)
                if not board_result.get("success"):
                    return {
                        "success": False,
                        "error": "BOARD_NOT_FOUND",
                        "message": f"I couldn't find a board called '{board_name}'."
                    }
                board_id = board_result["data"]["id"]
            
            list_result = await trello_find_list_by_name(board_id, list_name)
            if not list_result.get("success"):
                return {
                    "success": False,
                    "error": "LIST_NOT_FOUND",
                    "message": f"I couldn't find a list called '{list_name}'."
                }
            list_id = list_result["data"]["id"]
        
        result = await trello_list_cards(list_id)
        if not result.get("success"):
            return result
        
        cards = result["data"]
        message = _format_card_list(cards)
        
        return {
            "success": True,
            "message": message,
            "data": cards
        }
    
    # Create task
    if action == "create_task":
        if not title and not card_name:
            return {
                "success": False,
                "error": "MISSING_TITLE",
                "message": "What should I name this task?"
            }
        
        task_name = title or card_name
        
        if not board_id and not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which board should I create this task on?"
            }
        
        if board_name and not board_id:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                return {
                    "success": False,
                    "error": "BOARD_NOT_FOUND",
                    "message": f"I couldn't find a board called '{board_name}'."
                }
            board_id = board_result["data"]["id"]
        
        if not list_id:
            if list_name:
                list_result = await trello_find_list_by_name(board_id, list_name)
                if not list_result.get("success"):
                    return {
                        "success": False,
                        "error": "LIST_NOT_FOUND",
                        "message": f"I couldn't find a list called '{list_name}'."
                    }
                list_id = list_result["data"]["id"]
            else:
                lists_result = await trello_list_lists(board_id)
                if not lists_result.get("success"):
                    return lists_result
                
                lists = lists_result["data"]
                if not lists:
                    return {
                        "success": False,
                        "error": "NO_LISTS",
                        "message": "This board has no lists. Please create a list first."
                    }
                list_id = lists[0]["id"]
        
        result = await trello_create_card(
            list_id=list_id,
            name=task_name,
            description=description,
            due=due,
            labels=labels,
            members=members
        )
        
        if not result.get("success"):
            return result
        
        card = result["data"]
        message = f"Task '{task_name}' has been created."
        
        return {
            "success": True,
            "message": message,
            "data": card
        }
    
    # Update task
    if action == "update_task":
        if not card_id and not card_name:
            return {
                "success": False,
                "error": "MISSING_CARD",
                "message": "Which task should I update?"
            }
        
        if card_name and not card_id:
            if not board_id and not board_name:
                return {
                    "success": False,
                    "error": "MISSING_BOARD",
                    "message": "Which board is this task on?"
                }
            
            if board_name and not board_id:
                board_result = await trello_find_board_by_name(board_name)
                if not board_result.get("success"):
                    return {
                        "success": False,
                        "error": "BOARD_NOT_FOUND",
                        "message": f"I couldn't find a board called '{board_name}'."
                    }
                board_id = board_result["data"]["id"]
            
            card_result = await trello_find_card_by_name(board_id, card_name)
            if not card_result.get("success"):
                return {
                    "success": False,
                    "error": "CARD_NOT_FOUND",
                    "message": f"I couldn't find a task called '{card_name}'."
                }
            card_id = card_result["data"]["id"]
        
        if not fields:
            fields = {}
        
        if title:
            fields["name"] = title
        if description:
            fields["description"] = description
        if due:
            fields["due"] = due
        if labels:
            fields["labels"] = labels
        if members:
            fields["members"] = members
        
        result = await trello_update_card(card_id, fields)
        
        if not result.get("success"):
            return result
        
        card = result["data"]
        message = f"Task '{card.get('name', 'Untitled')}' has been updated."
        
        return {
            "success": True,
            "message": message,
            "data": card
        }
    
    # Move task
    if action == "move_task":
        if not card_id and not card_name:
            return {
                "success": False,
                "error": "MISSING_CARD",
                "message": "Which task should I move?"
            }
        
        if card_name and not card_id:
            if not board_id and not board_name:
                return {
                    "success": False,
                    "error": "MISSING_BOARD",
                    "message": "Which board is this task on?"
                }
            
            if board_name and not board_id:
                board_result = await trello_find_board_by_name(board_name)
                if not board_result.get("success"):
                    return {
                        "success": False,
                        "error": "BOARD_NOT_FOUND",
                        "message": f"I couldn't find a board called '{board_name}'."
                    }
                board_id = board_result["data"]["id"]
            
            card_result = await trello_find_card_by_name(board_id, card_name)
            if not card_result.get("success"):
                return {
                    "success": False,
                    "error": "CARD_NOT_FOUND",
                    "message": f"I couldn't find a task called '{card_name}'."
                }
            card_id = card_result["data"]["id"]
        
        if not list_id and not list_name:
            return {
                "success": False,
                "error": "MISSING_TARGET_LIST",
                "message": "Which list should I move this task to?"
            }
        
        if list_name and not list_id:
            if not board_id and not board_name:
                return {
                    "success": False,
                    "error": "MISSING_BOARD",
                    "message": "Which board is the target list on?"
                }
            
            if board_name and not board_id:
                board_result = await trello_find_board_by_name(board_name)
                if not board_result.get("success"):
                    return {
                        "success": False,
                        "error": "BOARD_NOT_FOUND",
                        "message": f"I couldn't find a board called '{board_name}'."
                    }
                board_id = board_result["data"]["id"]
            
            list_result = await trello_find_list_by_name(board_id, list_name)
            if not list_result.get("success"):
                return {
                    "success": False,
                    "error": "LIST_NOT_FOUND",
                    "message": f"I couldn't find a list called '{list_name}'."
                }
            list_id = list_result["data"]["id"]
        
        result = await trello_move_card(card_id, list_id, board_id)
        
        if not result.get("success"):
            return result
        
        card = result["data"]
        message = f"Task '{card.get('name', 'Untitled')}' has been moved."
        
        return {
            "success": True,
            "message": message,
            "data": card
        }
    
    # Delete task
    if action == "delete_task":
        if not card_id and not card_name:
            return {
                "success": False,
                "error": "MISSING_CARD",
                "message": "Which task should I delete?"
            }
        
        if card_name and not card_id:
            if not board_id and not board_name:
                return {
                    "success": False,
                    "error": "MISSING_BOARD",
                    "message": "Which board is this task on?"
                }
            
            if board_name and not board_id:
                board_result = await trello_find_board_by_name(board_name)
                if not board_result.get("success"):
                    return {
                        "success": False,
                        "error": "BOARD_NOT_FOUND",
                        "message": f"I couldn't find a board called '{board_name}'."
                    }
                board_id = board_result["data"]["id"]
            
            card_result = await trello_find_card_by_name(board_id, card_name)
            if not card_result.get("success"):
                return {
                    "success": False,
                    "error": "CARD_NOT_FOUND",
                    "message": f"I couldn't find a task called '{card_name}'."
                }
            card_id = card_result["data"]["id"]
            card_name = card_result["data"].get("name", "this task")
        
        if not confirm_delete:
            return {
                "success": False,
                "error": "CONFIRMATION_REQUIRED",
                "message": f"Are you sure you want to delete '{card_name}'?"
            }
        
        result = await trello_delete_card(card_id)
        
        if not result.get("success"):
            return result
        
        message = f"Task '{card_name}' has been deleted."
        
        return {
            "success": True,
            "message": message,
            "data": result["data"]
        }
    
    # Search tasks
    if action == "search_tasks":
        if not keyword:
            return {
                "success": False,
                "error": "MISSING_KEYWORD",
                "message": "What should I search for?"
            }
        
        board_ids = None
        if board_id:
            board_ids = [board_id]
        elif board_name:
            board_result = await trello_find_board_by_name(board_name)
            if board_result.get("success"):
                board_ids = [board_result["data"]["id"]]
        
        result = await trello_search_cards(keyword, board_ids)
        
        if not result.get("success"):
            return result
        
        cards = result["data"]
        message = _format_card_list(cards)
        
        return {
            "success": True,
            "message": message,
            "data": cards
        }
    
    # Filter tasks by due date
    if action == "filter_by_due":
        if not board_id and not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which board should I check?"
            }
        
        if board_name and not board_id:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                return {
                    "success": False,
                    "error": "BOARD_NOT_FOUND",
                    "message": f"I couldn't find a board called '{board_name}'."
                }
            board_id = board_result["data"]["id"]
        
        cards_result = await trello_get_board_cards(board_id)
        if not cards_result.get("success"):
            return cards_result
        
        cards = cards_result["data"]
        filter_result = await trello_filter_cards_by_due_date(cards, filter_type or "overdue")
        
        if not filter_result.get("success"):
            return filter_result
        
        filtered_cards = filter_result["data"]
        message = _format_card_list(filtered_cards)
        
        return {
            "success": True,
            "message": message,
            "data": filtered_cards
        }
    
    # Group by status
    if action == "group_by_status":
        if not board_id and not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which board should I check?"
            }
        
        if board_name and not board_id:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                return {
                    "success": False,
                    "error": "BOARD_NOT_FOUND",
                    "message": f"I couldn't find a board called '{board_name}'."
                }
            board_id = board_result["data"]["id"]
        
        cards_result = await trello_get_board_cards(board_id)
        if not cards_result.get("success"):
            return cards_result
        
        cards = cards_result["data"]
        group_result = await trello_group_cards_by_status(cards)
        
        if not group_result.get("success"):
            return group_result
        
        grouped = group_result["data"]
        message = _format_grouped_cards(grouped)
        
        return {
            "success": True,
            "message": message,
            "data": grouped
        }
    
    # Create board
    if action == "create_board":
        if not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD_NAME",
                "message": "What should I name this board?"
            }
        
        result = await trello_create_board(board_name, description)
        
        if not result.get("success"):
            return result
        
        board = result["data"]
        message = f"Board '{board_name}' has been created."
        
        return {
            "success": True,
            "message": message,
            "data": board
        }
    
    # Create list
    if action == "create_list":
        if not list_name:
            return {
                "success": False,
                "error": "MISSING_LIST_NAME",
                "message": "What should I name this list?"
            }
        
        if not board_id and not board_name:
            return {
                "success": False,
                "error": "MISSING_BOARD",
                "message": "Which board should I create this list on?"
            }
        
        if board_name and not board_id:
            board_result = await trello_find_board_by_name(board_name)
            if not board_result.get("success"):
                return {
                    "success": False,
                    "error": "BOARD_NOT_FOUND",
                    "message": f"I couldn't find a board called '{board_name}'."
                }
            board_id = board_result["data"]["id"]
        
        result = await trello_create_list(board_id, list_name)
        
        if not result.get("success"):
            return result
        
        list_data = result["data"]
        message = f"List '{list_name}' has been created."
        
        return {
            "success": True,
            "message": message,
            "data": list_data
        }
    
    return {
        "success": False,
        "error": "INVALID_ACTION",
        "message": "I don't understand that Trello action."
    }
