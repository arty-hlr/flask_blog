import os

username = 'flo_admin'
admin_hash = '706e389c2d834134a36820fe6257befe78297c7f981d462abb24eb67e3d35bd8df84f7dcc78793f26aacc946e76669b94405376b356628cdc116cce99a826943'
if not os.path.exists('session_key'):
    session_key = os.urandom(12)
    open('session_key','wb').write(session_key)
else:
    session_key = open('session_key','rb').read()

