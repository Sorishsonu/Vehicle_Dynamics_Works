from database import migrate, save_photo
from string import Template
import getpass, sys, sqlite3, secrets, hashlib, hmac, os, csv, io, html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from datetime import datetime, timezone, timedelta
from pathlib import Path
from http.cookies import SimpleCookie
BASE=Path(__file__).resolve().parent
IST=timezone(timedelta(hours=5,minutes=30))
def now(): return datetime.now(IST)
def db():
 c=sqlite3.connect(BASE/'attendance.db',timeout=15); c.row_factory=sqlite3.Row; return c
def hashpw(p,s): return hashlib.pbkdf2_hmac('sha256',p.encode(),s.encode(),200000).hex()
def add(c,u,n,p,role):
 s=secrets.token_hex(16); c.execute('INSERT INTO members(id,name,salt,pw,role) VALUES(?,?,?,?,?)',(u,n,s,hashpw(p,s),role))
with db() as c:
 c.executescript('CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY,name TEXT,salt TEXT,pw TEXT,role TEXT); CREATE TABLE IF NOT EXISTS punches(id INTEGER PRIMARY KEY,member TEXT,day TEXT,session TEXT,inside TEXT,outside TEXT, UNIQUE(member,day,session)); CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT); CREATE TABLE IF NOT EXISTS logins(token TEXT PRIMARY KEY,member TEXT,expires REAL);')
 if not c.execute("SELECT 1 FROM members WHERE id='admin'").fetchone():
  p=getpass.getpass('Create administrator password (minimum 8 characters): ')
  while len(p)<8: p=getpass.getpass('Enter at least 8 characters: ')
  add(c,'admin','Administrator',p,'admin')
 c.execute("INSERT OR IGNORE INTO settings VALUES('session','001')")
with db() as c:
 c.executescript("CREATE TABLE IF NOT EXISTS sessions(day TEXT, session TEXT, start TEXT, end TEXT, topic TEXT, instructor TEXT, PRIMARY KEY(day,session)); CREATE TABLE IF NOT EXISTS roster(day TEXT, session TEXT, member TEXT, PRIMARY KEY(day,session,member));")
 for col in ('usn','year','department','semester','phone','email','joined'):
  if col not in [r[1] for r in c.execute('PRAGMA table_info(members)')]: c.execute(f"ALTER TABLE members ADD COLUMN {col} TEXT DEFAULT ''")
with db() as c:
 c.execute('CREATE TABLE IF NOT EXISTS reset_requests(member TEXT PRIMARY KEY, requested TEXT)')
if '--reset-admin' in sys.argv:
 p=getpass.getpass('New administrator password (minimum 8 characters): ')
 if len(p)<8: sys.exit('Password too short')
 if p!=getpass.getpass('Confirm password: '): sys.exit('Passwords do not match')
 with db() as c:
  salt=secrets.token_hex(16); c.execute("UPDATE members SET salt=?,pw=? WHERE id='admin'",(salt,hashpw(p,salt))); c.execute("DELETE FROM logins WHERE member='admin'")
 print('Administrator password updated.'); sys.exit(0)
with db() as c:
 migrate(c)
 from modules import migrate_extra
 migrate_extra(c)
 from upgrade import migrate as migrate_v12
 migrate_v12(c)
def photofield(): return '<label>Profile photo (optional)<input class="profile-file" type="file" accept="image/jpeg,image/png,image/webp"></label><input type="hidden" name="photo">'
def designation(r): return {"admin":"VD Lead / Admin","co-lead":"Co-Lead","junior":"Junior Engineer","trainee":"Trainee Engineer"}.get(r,r)
def esc(x): return html.escape(str(x or ''),quote=True)
def duration(r): return round((datetime.fromisoformat(r['outside'])-datetime.fromisoformat(r['inside'])).total_seconds()/60,2) if r['outside'] else ''
def form(action,body): return f'<form method="post"><input type="hidden" name="action" value="{action}">{body}</form>'
class H(BaseHTTPRequestHandler):
 def send(self,body,status=200,cookie=None,typ='text/html; charset=utf-8',download=False):
  self.send_response(status); self.send_header('Content-Type',typ); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self'; form-action 'self'; frame-ancestors 'none'")
  if cookie:self.send_header('Set-Cookie',cookie)
  if download:self.send_header('Content-Disposition','attachment; filename='+('attendance.xlsx' if isinstance(body,bytes) else 'attendance.csv'))
  self.end_headers(); self.wfile.write(body if isinstance(body,bytes) else body.encode('utf-8'))
 def user(self,c):
  k=SimpleCookie(); k.load(self.headers.get('Cookie','')); t=k.get('vd'); return c.execute('SELECT members.* FROM members JOIN logins ON members.id=logins.member WHERE token=? AND expires>? AND members.status="Active"',(t.value,now().timestamp())).fetchone() if t else None
 def page(self,c,u,msg='',cookie=None):
  tab=parse_qs(urlsplit(self.path).query).get('tab',['dashboard'])[0]
  def panel(title,content): return f'<section><h2>{title}</h2>{content}</section>'
  def table(headers,rows): return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
  def field(label,name,typ='text',extra=''): return f'<label>{label}<input name="{name}" type="{typ}" {extra}></label>'
  memberfields=field('Member ID','id',extra='required')+field('Full name','name',extra='required')+field('USN','usn',extra='required')+'<label>Year<select name="year"><option>1</option><option>2</option><option>3</option><option>4</option></select></label>'+field('Password','pw','password','minlength="8" required')
  nav=''; b=''
  if not u:
   nav='<a href="/?tab=dashboard">Sign in</a><a href="/?tab=register">Register</a><a href="/?tab=forgot">Forgot password?</a>'
   if tab=='forgot': b=panel('Forgot password', '<p>Members: submit your ID and contact the administrator in person to verify your identity.</p>'+form('forgot',field('Member ID','id',extra='required')+'<button>Request password reset</button>')+'<p>Administrator: on the host laptop, stop the server and run RESET_ADMIN.bat. Restart the server afterwards.</p><a href="/">Back to sign in</a>')
   elif tab=='register': b=panel('Create member account',form('register',memberfields+''.join(field(k.title(),k) for k in ('department','semester','phone','email'))+photofield()+'<p>Photo is used only for your profile.</p><button>Register as Trainee Engineer</button>')+'<a href="/">Already registered? Sign in</a>')
   else: b=panel('Sign in',form('login',field('Member ID','id',extra='required')+field('Password','pw','password','required')+'<button>Sign in</button>')+'<p>New member? <a href="/?tab=register">Create an account</a></p><p><a href="/?tab=forgot">Forgot password?</a></p><small>Administrator ID: admin. Set or reset your password on the server laptop.</small>')
  else:
   admin=u['role']=='admin'; tabs=[('dashboard','Dashboard'),('punch','Training punch'),('meetingpunch','Meeting punch'),('attendance','Attendance history'),('account','My account'),('statistics','Member statistics')]+([('members','Members'),('sessions','Sessions'),('reports','Reports'),('audit','Activity logs')] if admin else [])
   tabs += [('profile','Personnel profile'),('meetings','Meetings'),('work','Work Done')] + ([('directory','Member directory')] if admin or u['role']=='co-lead' else [])
   nav=''.join(f'<a href="/?tab={k}" class="{"active" if tab==k else ""}">{v}</a>' for k,v in tabs)+form('logout','<button class="secondary">Sign out</button>')
   day=now().date().isoformat(); sn=c.execute("SELECT v FROM settings WHERE k='session'").fetchone()[0]; sess=c.execute('SELECT * FROM sessions WHERE day=? AND session=?',(day,sn)).fetchone()
   from modules import render
   extra=render(c,u,tab,parse_qs(urlsplit(self.path).query),panel,table,field,form,esc,now,designation)
   if extra is not None: b=extra
   elif tab=='statistics':
    people=c.execute("SELECT * FROM members WHERE role!='admin'"+('' if admin or u['role']=='co-lead' else ' AND id=?'),() if admin or u['role']=='co-lead' else (u['id'],)).fetchall()
    rows=[]
    for m in people:
     total=qualified=absent=late=0
     for x in c.execute('SELECT s.*,p.inside,p.outside FROM roster r JOIN sessions s ON s.day=r.day AND s.session=r.session LEFT JOIN punches p ON p.day=r.day AND p.session=r.session AND p.member=r.member WHERE r.member=?',(m['id'],)):
      st=datetime.fromisoformat(x['day']+'T'+x['start']).replace(tzinfo=IST); en=datetime.fromisoformat(x['day']+'T'+x['end']).replace(tzinfo=IST)
      if now()<en: continue
      total+=1
      if not x['inside']: absent+=1; continue
      i=datetime.fromisoformat(x['inside']); late+= (i-st).total_seconds()>300
      if x['outside'] and max(0,(min(datetime.fromisoformat(x['outside']),en)-max(i,st)).total_seconds())>=.75*(en-st).total_seconds(): qualified+=1
     rows.append((m['id'],m['name'],designation(m['role']),total,qualified,absent,late,f'{100*qualified/total:.1f}%' if total else 'N/A'))
    b=panel('Member statistics',table(['ID','Name','Designation','Ended sessions','Qualified','Absent','Late arrivals','Attendance'],rows))
   elif tab=='members' and admin:
    b=panel('Add member',form('add',memberfields+'<label>Role<select name="role"><option value="trainee">Trainee Engineer</option><option value="junior">Junior Engineer</option><option value="co-lead">Co-Lead</option></select></label><button>Add member</button>'))+panel('Member directory',table(['ID','Name','USN','Year','Role'],[(*tuple(r)[:4],designation(r["role"])) for r in c.execute("SELECT id,name,usn,year,role FROM members WHERE role!='admin' ORDER BY id")]))+panel('Official editing','<a href="/?tab=directory">Open member directory to edit official records</a>')

    b+=panel('Password reset requests',table(['Member ID','Name','Requested (IST)'],[tuple(r) for r in c.execute('SELECT m.id,m.name,r.requested FROM reset_requests r JOIN members m ON m.id=r.member ORDER BY r.requested DESC')])+ '<p>Verify the member identity in person before resetting. Share the temporary password privately.</p>'+form('reset_member',field('Member ID','id',extra='required')+field('Temporary password','pw','password','minlength="8" required')+field('Confirm temporary password','confirm','password','required')+'<button>Reset member password</button>'))
   elif tab=='sessions' and admin:
    b=panel('Configure today’s session',form('session',field('Session number (1–250)','number','number','min="1" max="250" required')+field('Scheduled start','start','time','required')+field('Scheduled end','end','time','required')+field('Topic','topic')+field('Instructor','instructor')+'<button>Activate session</button>'))+panel('Session register',table(['Date','Session','Start','End','Topic','Instructor'],[tuple(r) for r in c.execute('SELECT day,session,start,end,topic,instructor FROM sessions ORDER BY day DESC,session DESC')]))
   elif tab=='reports' and admin:
    b=panel('Export printable Excel report','<p>Includes attendance register, summary, sessions and member database.</p><form method="get" action="/excel">'+field('From date','from','date')+field('To date','to','date')+'<label>Role<select name="role"><option value="all">All members</option><option value="junior">Junior Engineer</option><option value="co-lead">Co-Lead</option><option value="trainee">Trainee Engineer</option></select></label><button>Download Excel (.xlsx)</button></form>')
   elif tab=='account':
    b=panel('Personal information',table(['Field','Value'],[(k.replace('_',' ').title(),u[k]) for k in ('id','name','usn','year','department','semester','phone','email','joined')])+form('v12_request',field('Request official information correction','request',extra='required')+'<button>Submit request</button>'))+panel('My account',f'<p>{esc(u["name"])} · {esc(u["id"])} · {esc(designation(u["role"]))}</p>'+form('password',field('Current password','old','password','required')+field('New password','pw','password','minlength="8" required')+'<button>Change password</button>'))
    b+=panel('Profile photograph', ('<img class="avatar" src="/profile-photo" alt="Your profile photo">' if c.execute('SELECT 1 FROM profile_photos WHERE member=?',(u['id'],)).fetchone() else '<p>No profile photo uploaded.</p>')+form('photo',photofield()+'<button>Change profile photo</button>'))
   elif tab=='punch':
    b=panel('Training attendance punch',f'<p>{esc(u["name"])} · {esc(u["id"])}</p>')
    r=c.execute('SELECT * FROM punches WHERE member=? AND outside IS NULL',(u['id'],)).fetchone(); done=c.execute('SELECT * FROM punches WHERE member=? AND day=? AND session=?',(u['id'],day,sn)).fetchone()
    detail=f'<p>Session {esc(sn)} · {esc(sess["topic"])} · {esc(sess["start"])}–{esc(sess["end"])}</p>' if sess else '<p>No session configured for today.</p>'
    if r: detail+=f'<p>Checked in: {esc(datetime.fromisoformat(r["inside"]).strftime("%I:%M:%S %p"))}</p>'+form('out','<button class="out">Punch OUT</button>')
    elif done: detail+='<p>Session completed.</p>'
    elif sess and not admin: detail+=form('in','<button class="in">Punch IN</button>')
    b+=panel('Current session',detail)
   elif tab=='audit' and admin:
    b=panel('Official modification history',table(['Member','Actor','Time','Reason','Changes'],[tuple(r) for r in c.execute('SELECT member,actor,stamp,reason,changes FROM audit ORDER BY id DESC')]))+panel('Correction requests',''.join('<p>'+esc(r['member'])+' · '+esc(r['request'])+' · '+esc(r['status'])+'</p>'+form('v12_resolve',f'<input type="hidden" name="rid" value="{r["id"]}"><button>Mark reviewed</button>') for r in c.execute('SELECT * FROM corrections ORDER BY id DESC')))
   elif tab=='attendance':
    rows=c.execute('SELECT p.*,m.name FROM punches p JOIN members m ON p.member=m.id '+('' if admin else 'WHERE member=? ')+'ORDER BY p.id DESC',() if admin else (u['id'],)).fetchall()
    b=panel('Attendance history',table(['Member','Date','Session','Punch IN','Punch OUT','Minutes','Status'],[(r['member']+' / '+r['name'],r['day'],r['session'],datetime.fromisoformat(r['inside']).strftime('%H:%M:%S'),datetime.fromisoformat(r['outside']).strftime('%H:%M:%S') if r['outside'] else '—',duration(r),'Completed' if r['outside'] else 'Checked in') for r in rows]))
   else:
    b=f'<h1>Welcome, {esc(u["name"])}</h1><p class="muted">{esc(designation(u["role"]))} portal</p>'
    if admin:
     counts=[('Co-Leads',c.execute("SELECT count(*) FROM members WHERE role='co-lead'").fetchone()[0]),('Junior Engineers',c.execute("SELECT count(*) FROM members WHERE role='junior'").fetchone()[0]),('Trainee Engineers',c.execute("SELECT count(*) FROM members WHERE role='trainee'").fetchone()[0]),('Members',c.execute("SELECT count(*) FROM members WHERE role!='admin'").fetchone()[0]),('Sessions',c.execute('SELECT count(*) FROM sessions').fetchone()[0]),('Today checked in',c.execute('SELECT count(DISTINCT member) FROM punches WHERE day=?',(day,)).fetchone()[0]),('Currently inside',c.execute('SELECT count(*) FROM punches WHERE outside IS NULL').fetchone()[0])]
     b+='<div class="metrics">'+''.join(f'<section><small>{k}</small><strong>{v}</strong></section>' for k,v in counts)+'</div>'
    b+=panel('Attendance','<a href="/?tab=punch">Training attendance punch</a> · <a href="/?tab=meetingpunch">Meeting attendance punch</a>')
  layout=Template((BASE/'templates/layout.html').read_text(encoding='utf-8'))
  self.send(layout.substitute(nav=nav,guest='' if u else 'guest',timestamp=int(now().timestamp()*1000),notice=f'<p class="notice">{esc(msg)}</p>' if msg else '',content=b),cookie=cookie)
 def do_GET(self):
  assets={'/static/profile.js':('profile.js','application/javascript'),'/static/style.css':('style.css','text/css'),'/static/clock.js':('clock.js','application/javascript'),'/static/racecar.svg':('racecar.svg','image/svg+xml')}
  if self.path in assets:
   name,typ=assets[self.path]; return self.send((BASE/'static'/name).read_bytes(),typ=typ)
  with db() as c:
   u=self.user(c)
   from modules import download_file
   if urlsplit(self.path).path=='/attachment': return download_file(self,c,u)
   if urlsplit(self.path).path=='/profile-photo':
    if not u:return self.send('Forbidden',403)
    mid=parse_qs(urlsplit(self.path).query).get('id',[u['id']])[0]
    if mid!=u['id'] and u['role'] not in ('admin','co-lead'):return self.send('Forbidden',403)
    r=c.execute('SELECT photo FROM profile_photos WHERE member=?',(mid,)).fetchone()
    return self.send(r[0],typ='image/jpeg') if r else self.send('Not found',404)
   if urlsplit(self.path).path=='/excel':
    if not u or u['role']!='admin':return self.send('Forbidden',403)
    from excel_report import report
    return self.send(report(c,parse_qs(urlsplit(self.path).query),now()),typ='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',download=True)
   if self.path=='/export':
    if not u or u['role']!='admin':return self.send('Forbidden',403)
    f=io.StringIO(); w=csv.writer(f); w.writerow(['Member ID','Name','Date','Day','Session','Punch IN IST','Punch OUT IST','Duration minutes','Status'])
    def safe(v): return "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v
    for r in c.execute('SELECT p.*,m.name FROM punches p JOIN members m ON p.member=m.id'):w.writerow([safe(r['member']),safe(r['name']),r['day'],datetime.fromisoformat(r['day']).strftime('%A'),r['session'],r['inside'],r['outside'],duration(r),'Completed' if r['outside'] else 'Checked in'])
    return self.send('\ufeff'+f.getvalue(),typ='text/csv; charset=utf-8',download=True)
   self.page(c,u)
 def do_POST(self):
  if self.headers.get('Origin') and self.headers['Origin']!='http://'+self.headers.get('Host',''):return self.send('Forbidden',403)
  size=int(self.headers.get('Content-Length','0')); 
  if size>85000000:return self.send('Too large',413)
  p=parse_qs(self.rfile.read(size).decode()); g=lambda k:p.get(k,[''])[0]; a=g('action')
  with db() as c:
   c.execute('BEGIN IMMEDIATE'); u=self.user(c); msg=''; cookie=None
   if a=='login':
    r=c.execute('SELECT * FROM members WHERE id=?',(g('id'),)).fetchone()
    if r and r['status']=='Active' and hmac.compare_digest(r['pw'],hashpw(g('pw'),r['salt'])):
     t=secrets.token_urlsafe(32); c.execute('INSERT INTO logins VALUES(?,?,?)',(t,r['id'],now().timestamp()+43200)); u=r; cookie=f'vd={t}; HttpOnly; SameSite=Strict; Path=/'; msg='Logged in'
    else:msg='Incorrect login'
   elif a=='register' and not u:
    if all(g(k).strip() for k in ('id','name','usn','year')) and len(g('pw'))>=8:
     try:
      c.execute('SAVEPOINT registration')
      mid=g('id').strip()
      add(c,mid,g('name').strip(),g('pw'),'trainee')
      c.execute('UPDATE members SET usn=?,year=?,department=?,semester=?,phone=?,email=?,joined=? WHERE id=?',(g('usn'),g('year'),g('department'),g('semester'),g('phone'),g('email'),now().date().isoformat(),mid))
      if g('photo'):save_photo(c,mid,g('photo'))
      c.execute('RELEASE registration'); msg='Registration saved. Please log in.'
     except Exception:
      c.execute('ROLLBACK TO registration'); c.execute('RELEASE registration'); msg='Registration failed: duplicate ID or invalid profile photo. Try again.'
    else:msg='Complete all fields and use at least 8 password characters'
   elif a=='forgot' and not u:
    c.execute("INSERT OR IGNORE INTO reset_requests SELECT id,? FROM members WHERE id=? AND role!='admin'",(now().isoformat(),g('id').strip())); msg='If this is a member account, your request has been recorded. Contact the administrator. Administrators must use the local recovery utility.'
   elif not u:msg='Please log in' 
   elif a.startswith('extra_'):
    from modules import action
    msg=action(c,u,a,g,now)
   elif a=='logout':
    k=SimpleCookie(); k.load(self.headers.get('Cookie','')); c.execute('DELETE FROM logins WHERE token=?',(k['vd'].value,)); u=None; cookie='vd=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict'
   elif a.startswith('v12_'):
    from upgrade import action
    msg=action(c,u,a,g,now,hashpw,save_photo)
   elif a=='password':
    if len(g('pw'))>=8 and hmac.compare_digest(u['pw'],hashpw(g('old'),u['salt'])):
     salt=secrets.token_hex(16); c.execute('UPDATE members SET salt=?,pw=? WHERE id=?',(salt,hashpw(g('pw'),salt),u['id'])); msg='Password changed'
    else:msg='Incorrect current password or new password too short'
   elif a=='reset_member' and u['role']=='admin':
    if len(g('pw'))<8 or g('pw')!=g('confirm'):msg='Passwords must match and contain at least 8 characters'
    else:
     salt=secrets.token_hex(16); mid=g('id').strip(); n=c.execute("UPDATE members SET salt=?,pw=? WHERE id=? AND role!='admin'",(salt,hashpw(g('pw'),salt),mid)).rowcount
     if n:
      c.execute('DELETE FROM logins WHERE member=?',(mid,)); c.execute('DELETE FROM reset_requests WHERE member=?',(mid,)); msg='Member password reset. Share it privately and ask the member to change it.'
     else:msg='Member not found'
   elif a=='photo':
    try:
     save_photo(c,u['id'],g('photo')); msg='Profile photo saved'
    except Exception:msg='Select a valid profile photo'
   elif a=='in':
    d=now(); s=c.execute("SELECT v FROM settings WHERE k='session'").fetchone()[0]
    if u['role']=='admin' or not c.execute('SELECT 1 FROM sessions WHERE day=? AND session=?',(d.date().isoformat(),s)).fetchone():msg='No available session'
    elif c.execute('SELECT 1 FROM punches WHERE member=? AND outside IS NULL',(u['id'],)).fetchone():msg='Already checked in'
    else:
     try:c.execute('INSERT INTO punches(member,day,session,inside) VALUES(?,?,?,?)',(u['id'],d.date().isoformat(),s,d.isoformat())); c.execute('INSERT OR IGNORE INTO roster VALUES(?,?,?)',(d.date().isoformat(),s,u['id'])); msg='Punch IN recorded'
     except sqlite3.IntegrityError:msg='Already attended this session today'
   elif a=='out':
    n=c.execute('UPDATE punches SET outside=? WHERE member=? AND outside IS NULL',(now().isoformat(),u['id'])).rowcount; msg='Punch OUT recorded' if n else 'No open punch'
   elif u['role']=='admin' and a=='session':
    if g('number').isdigit() and 1<=int(g('number'))<=250 and g('start') and g('end') and g('start')<g('end'):
     sn=f'{int(g("number")):03}'; day=now().date().isoformat()
     c.execute("UPDATE settings SET v=? WHERE k='session'",(sn,))
     c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?) ON CONFLICT(day,session) DO UPDATE SET start=excluded.start,end=excluded.end,topic=excluded.topic,instructor=excluded.instructor',(day,sn,g('start'),g('end'),g('topic'),g('instructor')))
     c.execute("INSERT OR IGNORE INTO roster SELECT ?,?,id FROM members WHERE role!='admin'",(day,sn)); msg='Session updated' 
    else:msg='Invalid session'
   elif u['role']=='admin' and a=='add':
    if g('id').strip() and g('name').strip() and len(g('pw'))>=8 and g('role') in ('junior','trainee','co-lead'):
     try:add(c,g('id').strip(),g('name').strip(),g('pw'),g('role')); c.execute('UPDATE members SET usn=?,year=? WHERE id=?',(g('usn'),g('year'),g('id').strip())); msg='Member added'
     except sqlite3.IntegrityError:msg='Member ID already exists'
    else:msg='Invalid member details'
   c.commit(); self.page(c,u,msg,cookie)
if __name__=='__main__':
 print('VDMS V12 | Open http://localhost:5000 in Chrome. Keep this window open.',flush=True)
 ThreadingHTTPServer(('0.0.0.0',5000),H).serve_forever()
