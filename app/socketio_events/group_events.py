"""Group-related WebSocket events for real-time updates."""

from flask import current_app
from flask_socketio import emit
from app.socketio_app import get_socketio
import json


def broadcast_expense_added(group_share_token, expense_data):
    """Broadcast new expense addition to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    # Format expense data for broadcast
    event_data = {
        'type': 'expense_added',
        'expense': {
            'id': expense_data.get('id'),
            'title': expense_data.get('title'),
            'amount': expense_data.get('amount'),
            'currency': expense_data.get('currency'),
            'paid_by_name': expense_data.get('paid_by_name'),
            'date': expense_data.get('date'),
            'category': expense_data.get('category')
        },
        'message': f"New expense: {expense_data.get('title')} - {expense_data.get('currency')}{expense_data.get('amount')}"
    }
    
    current_app.logger.info(f"Broadcasting expense_added to room {room_name}")
    socketio.emit('expense_update', event_data, room=room_name)


def broadcast_expense_updated(group_share_token, expense_data):
    """Broadcast expense update to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'expense_updated',
        'expense': {
            'id': expense_data.get('id'),
            'title': expense_data.get('title'),
            'amount': expense_data.get('amount'),
            'currency': expense_data.get('currency'),
            'paid_by_name': expense_data.get('paid_by_name'),
            'date': expense_data.get('date'),
            'category': expense_data.get('category')
        },
        'message': f"Updated expense: {expense_data.get('title')}"
    }
    
    current_app.logger.info(f"Broadcasting expense_updated to room {room_name}")
    socketio.emit('expense_update', event_data, room=room_name)


def broadcast_expense_deleted(group_share_token, expense_data):
    """Broadcast expense deletion to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'expense_deleted',
        'expense_id': expense_data.get('id'),
        'message': f"Deleted expense: {expense_data.get('title')}"
    }
    
    current_app.logger.info(f"Broadcasting expense_deleted to room {room_name}")
    socketio.emit('expense_update', event_data, room=room_name)


def broadcast_participant_joined(group_share_token, participant_data):
    """Broadcast new participant addition to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'participant_joined',
        'participant': {
            'id': participant_data.get('id'),
            'name': participant_data.get('name'),
            'email': participant_data.get('email'),
            'color': participant_data.get('color')
        },
        'message': f"{participant_data.get('name')} joined the group"
    }
    
    current_app.logger.info(f"Broadcasting participant_joined to room {room_name}")
    socketio.emit('participant_update', event_data, room=room_name)


def broadcast_participant_removed(group_share_token, participant_data):
    """Broadcast participant removal to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'participant_removed',
        'participant_id': participant_data.get('id'),
        'message': f"{participant_data.get('name')} left the group"
    }
    
    current_app.logger.info(f"Broadcasting participant_removed to room {room_name}")
    socketio.emit('participant_update', event_data, room=room_name)


def broadcast_participant_updated(group_share_token, participant_data):
    """Broadcast participant update to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'participant_updated',
        'participant': {
            'id': participant_data.get('id'),
            'name': participant_data.get('name'),
            'email': participant_data.get('email'),
            'color': participant_data.get('color')
        },
        'old_name': participant_data.get('old_name'),
        'message': f"Updated {participant_data.get('name')}"
    }
    
    current_app.logger.info(f"Broadcasting participant_updated to room {room_name}")
    socketio.emit('participant_update', event_data, room=room_name)


def broadcast_balance_updated(group_share_token, balance_data):
    """Broadcast balance recalculation to all group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'balance_updated',
        'balances': balance_data.get('balances', {}),
        'settlements': balance_data.get('settlements', []),
        'message': "Balances updated"
    }
    
    current_app.logger.info(f"Broadcasting balance_updated to room {room_name}")
    socketio.emit('balance_update', event_data, room=room_name)