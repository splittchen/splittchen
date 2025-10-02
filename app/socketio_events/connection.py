"""WebSocket connection handling with authentication."""

from flask import session, current_app, request
from flask_socketio import emit, join_room, leave_room, disconnect
from app.models import Group, Participant
from app.routes import verify_participant_access, verify_admin_access
import logging


def register_connection_handlers(socketio):
    """Register connection-related WebSocket event handlers."""
    
    @socketio.on('connect')
    def handle_connect(auth=None):
        """Handle new WebSocket connections."""
        client_id = request.sid
        current_app.logger.info(f"WebSocket connection attempt from {request.remote_addr} (ID: {client_id})")
        
        # Basic connection logging
        emit('connection_status', {
            'status': 'connected',
            'message': 'Connected to Splittchen real-time updates',
            'client_id': client_id
        })
    
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle WebSocket disconnections."""
        client_id = request.sid
        current_app.logger.info(f"WebSocket disconnection (ID: {client_id})")
    
    
    @socketio.on('join_group')
    def handle_join_group(data):
        """Join a group room for real-time updates."""
        client_id = request.sid
        share_token = data.get('share_token')
        
        if not share_token:
            current_app.logger.warning(f"Join group attempt without share_token (ID: {client_id})")
            emit('error', {'message': 'Share token required'})
            return
        
        # Verify user has access to this group
        participant, group = verify_participant_access(share_token)
        if not group:
            current_app.logger.warning(f"Join group attempt for invalid token {share_token[:6]}... (ID: {client_id})")
            emit('error', {'message': 'Invalid group access'})
            return
        
        # Join the group room
        room_name = f"group_{share_token}"
        join_room(room_name)
        
        # Check if user has admin access
        is_admin = verify_admin_access(share_token, group)
        if is_admin:
            admin_room_name = f"admin_{share_token}"
            join_room(admin_room_name)
            current_app.logger.info(f"Client {client_id} joined admin room {admin_room_name}")
        
        current_app.logger.info(f"Client {client_id} joined group room {room_name} for group '{group.name}'")
        
        # Send confirmation with group info
        emit('group_joined', {
            'group': {
                'name': group.name,
                'share_token': share_token,
                'member_count': len(group.participants),
                'is_admin': is_admin
            },
            'room': room_name,
            'message': f'Joined real-time updates for {group.name}'
        })
    
    
    @socketio.on('leave_group')
    def handle_leave_group(data):
        """Leave a group room."""
        client_id = request.sid
        share_token = data.get('share_token')
        
        if not share_token:
            emit('error', {'message': 'Share token required'})
            return
        
        # Leave both regular and admin rooms
        room_name = f"group_{share_token}"
        admin_room_name = f"admin_{share_token}"
        
        leave_room(room_name)
        leave_room(admin_room_name)
        
        current_app.logger.info(f"Client {client_id} left group rooms for token {share_token[:6]}...")
        
        emit('group_left', {
            'share_token': share_token,
            'message': 'Left group real-time updates'
        })
    
    
    @socketio.on('ping')
    def handle_ping():
        """Handle client ping for connection testing."""
        emit('pong', {'timestamp': current_app.logger.name})  # Simple pong response


# Import this function to register handlers
def init_connection_handlers(socketio):
    """Initialize connection handlers."""
    register_connection_handlers(socketio)
    # Note: Logging will be available when the handlers are called