"""Browser notification handling for WebSocket events."""

from flask import current_app
from flask_socketio import emit
from app.socketio_app import get_socketio


def send_browser_notification(group_share_token, notification_data, exclude_sender=None):
    """Send browser notification to group members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    # Format notification for browser display
    event_data = {
        'type': 'browser_notification',
        'notification': {
            'title': notification_data.get('title', 'Splittchen Update'),
            'body': notification_data.get('body', ''),
            'icon': notification_data.get('icon', '/static/favicon-32x32.png'),
            'badge': notification_data.get('badge', '/static/favicon-32x32.png'),
            'tag': notification_data.get('tag', f"group_{group_share_token}"),
            'requireInteraction': notification_data.get('require_interaction', False),
            'silent': notification_data.get('silent', False)
        },
        'action': notification_data.get('action', {}),  # Optional click action
        'exclude_sender': exclude_sender
    }
    
    current_app.logger.info(f"Sending browser notification to room {room_name}: {notification_data.get('title')}")
    socketio.emit('notification', event_data, room=room_name)


def create_expense_notification(expense_data):
    """Create notification data for new expense."""
    return {
        'title': f"New expense in {expense_data.get('group_name', 'your group')}",
        'body': f"{expense_data.get('paid_by_name')} added {expense_data.get('currency')}{expense_data.get('amount')} for '{expense_data.get('title')}'",
        'tag': f"expense_{expense_data.get('id')}",
        'action': {
            'type': 'open_group',
            'share_token': expense_data.get('share_token'),
            'tab': 'expenses'
        }
    }


def create_participant_notification(participant_data):
    """Create notification data for new participant."""
    return {
        'title': f"New member in {participant_data.get('group_name', 'your group')}",
        'body': f"{participant_data.get('name')} joined the group",
        'tag': f"participant_{participant_data.get('id')}",
        'action': {
            'type': 'open_group',
            'share_token': participant_data.get('share_token'),
            'tab': 'participants'
        }
    }


def create_settlement_notification(settlement_data):
    """Create notification data for group settlement."""
    return {
        'title': f"Group settled: {settlement_data.get('group_name', 'your group')}",
        'body': f"Settlement completed for {settlement_data.get('period_name', 'the group')}",
        'tag': f"settlement_{settlement_data.get('group_id')}",
        'require_interaction': True,  # Important settlement notification
        'action': {
            'type': 'open_group',
            'share_token': settlement_data.get('share_token'),
            'tab': 'balances'
        }
    }