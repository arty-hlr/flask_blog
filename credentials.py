import os

username = 'flo_admin'
admin_hash = '394a5a7a258203378db259a67fe4b98c44b4a9173c6ae7b731482296065b88008d447052e455e6e6ab307fc59551e24fcacf946095bb3b6990d5ef52767d9507'
if not os.path.exists('session_key'):
    session_key = os.urandom(12)
    open('session_key','wb').write(session_key)
else:
    session_key = open('session_key','rb').read()

