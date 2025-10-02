"""Admin-specific WebSocket events for group management."""

from flask import current_app
from flask_socketio import emit
from app.socketio_app import get_socketio


def broadcast_group_settled(group_share_token, settlement_data):
    """Broadcast group settlement to all members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'group_settled',
        'settlement': {
            'settled_at': settlement_data.get('settled_at'),
            'period_name': settlement_data.get('period_name'),
            'final_settlement': settlement_data.get('final_settlement', False)
        },
        'message': f"Group settled: {settlement_data.get('period_name', 'Final settlement')}"
    }
    
    current_app.logger.info(f"Broadcasting group_settled to room {room_name}")
    socketio.emit('admin_action', event_data, room=room_name)


def broadcast_group_reopened(group_share_token):
    """Broadcast group reopening to all members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'group_reopened',
        'message': "Group has been reopened by admin"
    }
    
    current_app.logger.info(f"Broadcasting group_reopened to room {room_name}")
    socketio.emit('admin_action', event_data, room=room_name)


def broadcast_group_deleted(group_share_token):
    """Broadcast group deletion warning to all members."""
    socketio = get_socketio()
    if not socketio:
        return
    
    room_name = f"group_{group_share_token}"
    
    event_data = {
        'type': 'group_deleted',
        'message': "This group has been permanently deleted by admin"
    }
    
    current_app.logger.info(f"Broadcasting group_deleted to room {room_name}")
    socketio.emit('admin_action', event_data, room=room_name)


def notify_admin_only(group_share_token, admin_data):
    """Send admin-only notifications."""
    socketio = get_socketio()
    if not socketio:
        return
    
    admin_room_name = f"admin_{group_share_token}"
    
    event_data = {
        'type': 'admin_notification',
        'data': admin_data,
        'message': admin_data.get('message', 'Admin notification')
    }
    
    current_app.logger.info(f"Sending admin notification to room {admin_room_name}")
    socketio.emit('admin_notification', event_data, room=admin_room_name)