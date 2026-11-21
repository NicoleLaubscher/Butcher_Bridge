"""ButcherBridge final-exam application; share one hosted MySQL database."""
import logging
import os
from datetime import date
from decimal import Decimal
from functools import wraps
from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from dotenv import load_dotenv
from pymysql.err import IntegrityError
from db import query, read_snapshot, transaction
from decision_engine import compare_plans, evaluate_optimised_plan, evaluate_plan
from group_formation_planner import GroupPlanningLimits

load_dotenv(override=True)
app=Flask(__name__)
app.secret_key=os.getenv('SECRET_KEY','')
app.config['SESSION_COOKIE_HTTPONLY']=True
app.config['SESSION_COOKIE_SAMESITE']='Lax'
app.config['SESSION_COOKIE_SECURE']=os.getenv('APP_ENV')=='production'
group_planning_defaults = GroupPlanningLimits()
app.config.from_mapping(
    GROUP_PLANNING_MAX_RETAILERS=os.getenv(
        'GROUP_PLANNING_MAX_RETAILERS', group_planning_defaults.max_retailers_per_bucket,
    ),
    GROUP_PLANNING_MAX_QUOTE_EVALUATIONS=os.getenv(
        'GROUP_PLANNING_MAX_QUOTE_EVALUATIONS', group_planning_defaults.max_quote_evaluations,
    ),
    GROUP_PLANNING_MAX_SEARCH_NODES=os.getenv(
        'GROUP_PLANNING_MAX_SEARCH_NODES', group_planning_defaults.max_search_nodes,
    ),
)
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')

ORDER_DETAILS = '''SELECT d.*,r.name AS retailer_name,p.name AS product_name,p.specification,
        w.label AS window_label FROM demand_orders d JOIN retailers r ON r.id=d.retailer_id
        JOIN products p ON p.id=d.product_id JOIN order_windows w ON w.id=d.window_id'''
OFFER_DETAILS = '''SELECT o.*,s.name AS supplier_name,s.service_area FROM supplier_offers o
        JOIN suppliers s ON s.id=o.supplier_id ORDER BY o.id'''
PRICE_TIERS = 'SELECT * FROM price_tiers ORDER BY min_quantity_kg'
ALLOCATIONS = 'SELECT offer_id, window_id, quantity_kg, status FROM allocations'


def require_login(fn):
    @wraps(fn)
    def inner(*args,**kwargs):
        if not session.get('signed_in'):
            if request.path.startswith('/api/'):
                return jsonify(error='Sign in first'),401
            return redirect(url_for('login'))
        return fn(*args,**kwargs)
    return inner

@app.route('/login',methods=['GET','POST'])
def login():
    error=None
    if request.method=='POST':
        from hmac import compare_digest
        password=os.getenv('APP_PASSWORD','')
        if password and compare_digest(request.form.get('password',''),password):
            session.clear(); session['signed_in']=True
            return redirect(url_for('home'))
        error='Incorrect demo password'
    return render_template('login.html',error=error)

@app.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


def lookup_data():
    return {'retailers':query('SELECT id,name,area FROM retailers ORDER BY name'),
            'products':query('SELECT id,name,specification FROM products ORDER BY name'),
            'windows':query('SELECT id,label,closes_at,status FROM order_windows ORDER BY id'),
            'suppliers':query('SELECT id,name,service_area FROM suppliers ORDER BY name')}

def all_orders():
    return query(ORDER_DETAILS + ' ORDER BY d.id DESC')

def all_offers():
    return query(OFFER_DETAILS)

def decision_results(*, optimised=False):
    orders = all_orders()
    offers = all_offers()
    tiers = query(PRICE_TIERS)
    allocations = query(ALLOCATIONS)
    if not optimised:
        batches, totals = evaluate_plan(orders, offers, tiers, allocations)
        return batches, totals, {}

    return evaluate_optimised_plan(orders, offers, tiers, allocations, limits=group_planning_limits())


def group_planning_limits():
    try:
        return GroupPlanningLimits(
            max_retailers_per_bucket=int(str(app.config['GROUP_PLANNING_MAX_RETAILERS'])),
            max_quote_evaluations=int(str(app.config['GROUP_PLANNING_MAX_QUOTE_EVALUATIONS'])),
            max_search_nodes=int(str(app.config['GROUP_PLANNING_MAX_SEARCH_NODES'])),
        )
    except ValueError:
        raise ValueError('Retailer grouping limits must be nonnegative integers.') from None


def comparison_results(*, include_metrics=False):
    as_of = date.today()
    limits = group_planning_limits()
    with read_snapshot() as read:
        orders = read(ORDER_DETAILS + " WHERE d.status='committed' ORDER BY d.id DESC")
        offers = read(OFFER_DETAILS)
        tiers = read(PRICE_TIERS)
        allocations = read(ALLOCATIONS)
        metrics = dashboard_metrics(read) if include_metrics else None
    summary, plans = compare_plans(orders, offers, tiers, allocations, as_of=as_of, limits=limits)
    return summary, plans, metrics


def dashboard_metrics(read=None):
    read = query if read is None else read
    stats=read('''SELECT COUNT(*) AS order_count,COALESCE(SUM(CASE WHEN status='committed' THEN quantity_kg ELSE 0 END),0) AS committed_kg FROM demand_orders''')[0]
    fulfil=read('''SELECT COUNT(*) AS n, COALESCE(SUM(f.delivered_kg),0) AS delivered,COALESCE(SUM(o.quantity_kg),0) AS ordered,
       COALESCE(SUM(CASE WHEN f.actual_days<=f.planned_days THEN 1 ELSE 0 END),0) AS on_time,
       COALESCE(SUM(CASE WHEN f.actual_days<=f.planned_days AND f.delivered_kg>=o.quantity_kg THEN 1 ELSE 0 END),0) AS otif
       FROM fulfilments f JOIN demand_orders o ON o.id=f.demand_order_id''')[0]
    n=int(fulfil['n']); ordered=float(fulfil['ordered'])
    return {'orders':int(stats['order_count']), 'committed_kg':float(stats['committed_kg']),
            'fill_pct':round(float(fulfil['delivered'])/ordered*100,1) if ordered else None,
            'on_time_pct':round(int(fulfil['on_time'])/n*100,1) if n else None,
            'otif_pct':round(int(fulfil['otif'])/n*100,1) if n else None}


@app.template_filter('rand_amount')
def rand_amount(value):
    amount = Decimal(value)
    sign = '-' if amount < 0 else ''
    whole, _, fraction = format(abs(amount), ',f').partition('.')
    return f"{sign}R{whole}.{fraction.rstrip('0').ljust(2, '0')}"


@app.get('/')
@require_login
def home():
    mode = 'optimised' if request.args.get('grouping') == 'optimised' else 'fixed'
    comparison, plans, metrics = comparison_results(include_metrics=True)
    return render_template('dashboard.html', batches=plans[mode], metrics=metrics,
                           comparison=comparison, mode=mode)

@app.get('/orders')
@require_login
def orders_page():
    return render_template('orders.html',orders=all_orders(),**lookup_data())

@app.get('/offers')
@require_login
def offers_page():
    offers=all_offers(); tiers=query('SELECT * FROM price_tiers ORDER BY offer_id,min_quantity_kg')
    return render_template('offers.html',offers=offers,tiers=tiers,**lookup_data())

@app.get('/fulfilment')
@require_login
def fulfilment_page():
    rows=query("SELECT d.id,r.name AS retailer_name,d.quantity_kg FROM demand_orders d JOIN retailers r ON r.id=d.retailer_id WHERE d.status='committed' ORDER BY d.id")
    return render_template('fulfilment.html',orders=rows,metrics=dashboard_metrics())

@app.get('/methodology')
@require_login
def methodology(): return render_template('methodology.html')


def body():
    data=request.get_json(silent=True)
    if not isinstance(data,dict): raise ValueError('Expected a JSON object')
    return data

def positive(data,key):
    try: n=Decimal(str(data[key]))
    except (KeyError,ValueError,TypeError,ArithmeticError): raise ValueError(f'{key} must be a number')
    if not n.is_finite() or n<=0: raise ValueError(f'{key} must be positive')
    return n

def nonnegative(data,key,default=0):
    try: n=Decimal(str(data.get(key,default)))
    except (ValueError,TypeError,ArithmeticError): raise ValueError(f'{key} must be a number')
    if not n.is_finite() or n<0: raise ValueError(f'{key} cannot be negative')
    return n

def identifier(data,key):
    try: n=int(data[key])
    except (KeyError,TypeError,ValueError): raise ValueError(f'{key} is required as an integer')
    if n<=0: raise ValueError(f'{key} must be positive')
    return n

def order_payload(d):
    try: needed=date.fromisoformat(str(d['needed_date']))
    except (KeyError,ValueError): raise ValueError('needed_date must be YYYY-MM-DD')
    if needed<date.today(): raise ValueError('needed_date cannot be in the past')
    area=str(d.get('delivery_area','')).strip()
    if not area or len(area)>100: raise ValueError('delivery_area is required (max 100 chars)')
    status=str(d.get('status','draft'))
    if status not in ('draft','committed','withdrawn'): raise ValueError('Invalid status')
    evidence=str(d.get('evidence_type','simulated'))
    if evidence not in ('primary','quoted','estimated','simulated'): raise ValueError('Invalid evidence type')
    return (identifier(d,'retailer_id'),identifier(d,'product_id'),identifier(d,'window_id'),needed.isoformat(),
            area,positive(d,'quantity_kg'),nonnegative(d,'baseline_price_per_kg'),nonnegative(d,'baseline_logistics_cost'),
            int(nonnegative(d,'baseline_trips',1)),nonnegative(d,'baseline_distance_km'),status,evidence,str(d.get('evidence_note',''))[:500])

@app.get('/api/orders')
@require_login
def api_orders():
    page=int(request.args.get('page','1'));size=int(request.args.get('size','20'))
    if not 1<=page<=100000 or not 1<=size<=100: raise ValueError('page must be positive and size between 1 and 100')
    status=request.args.get('status','')
    if status and status not in ('draft','committed','withdrawn','fulfilled'): raise ValueError('Invalid status filter')
    where=' WHERE d.status=%s' if status else ''
    params=[status] if status else []
    rows=query('''SELECT d.*,r.name AS retailer_name FROM demand_orders d JOIN retailers r ON r.id=d.retailer_id'''+where+' ORDER BY d.id DESC LIMIT %s OFFSET %s',params+[size,(page-1)*size])
    return jsonify(items=rows,page=page,size=size)

@app.get('/api/orders/<int:oid>')
@require_login
def api_order(oid):
    rows=query('SELECT * FROM demand_orders WHERE id=%s',(oid,))
    return (jsonify(rows[0]),200) if rows else (jsonify(error='Order not found'),404)

@app.post('/api/orders')
@require_login
def api_create_order():
    vals=order_payload(body())
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT status,closes_at FROM order_windows WHERE id=%s FOR UPDATE',(vals[2],))
            window=cur.fetchone()
            if not window or window['status']!='open' or window['closes_at'].date()<date.today(): raise ValueError('Order window is not open')
            cur.execute('''INSERT INTO demand_orders (retailer_id,product_id,window_id,needed_date,delivery_area,quantity_kg,baseline_price_per_kg,baseline_logistics_cost,baseline_trips,baseline_distance_km,status,evidence_type,evidence_note)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',vals)
            new_id=cur.lastrowid
    return jsonify(id=new_id,message='Order saved'),201

@app.patch('/api/orders/<int:oid>')
@require_login
def api_update_order(oid):
    data=body()
    allowed={'quantity_kg','baseline_price_per_kg','baseline_logistics_cost','status','evidence_note'}
    if not data or set(data)-allowed: raise ValueError('Unsupported or empty update fields')
    parts=[];params=[]
    for k,v in data.items():
        if k=='status':
            if v not in ('draft','committed','withdrawn'): raise ValueError('Invalid status')
            parsed=v
        elif k=='evidence_note': parsed=str(v)[:500]
        elif k=='quantity_kg': parsed=positive(data,k)
        else: parsed=nonnegative(data,k)
        parts.append(k+'=%s');params.append(parsed)
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT d.id,d.status,w.status AS window_status,w.closes_at FROM demand_orders d JOIN order_windows w ON w.id=d.window_id WHERE d.id=%s FOR UPDATE',(oid,))
            current=cur.fetchone()
            if not current: return jsonify(error='Order not found'),404
            if current['status']=='fulfilled': raise ValueError('Fulfilled orders cannot be changed')
            if current['window_status']!='open' or current['closes_at'].date()<date.today(): raise ValueError('Order window is closed; withdrawal requires administrator handling')
            cur.execute('UPDATE demand_orders SET '+','.join(parts)+' WHERE id=%s',params+[oid])
    return jsonify(id=oid,message='Order updated')

@app.get('/api/offers')
@require_login
def api_offers(): return jsonify(items=all_offers())

@app.post('/api/offers')
@require_login
def api_create_offer():
    d=body();tiers=d.get('tiers')
    if not isinstance(tiers,list) or not tiers: raise ValueError('Supply at least one price tier')
    if len(tiers)>20: raise ValueError('Maximum 20 tiers')
    rows=[]
    for t in tiers:
        if not isinstance(t,dict): raise ValueError('Invalid tier')
        rows.append((positive(t,'min_quantity_kg'),nonnegative(t,'price_per_kg')))
    if len({x[0] for x in rows})!=len(rows): raise ValueError('Duplicate price tier threshold')
    fill=nonnegative(d,'fill_rate')
    if fill>1: raise ValueError('fill_rate must be a fraction from 0 to 1')
    lead=int(nonnegative(d,'lead_days'))
    vals=(identifier(d,'supplier_id'),identifier(d,'product_id'),positive(d,'capacity_kg'),lead,fill,
          nonnegative(d,'fixed_delivery'),nonnegative(d,'variable_delivery_per_kg'),nonnegative(d,'handling_cost'),
          int(nonnegative(d,'coordinated_trips',1)),nonnegative(d,'coordinated_distance_km'),str(d.get('evidence_type','simulated')),
          str(d.get('evidence_note',''))[:500])
    if vals[-2] not in ('primary','quoted','estimated','simulated'): raise ValueError('Invalid evidence type')
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('''INSERT INTO supplier_offers (supplier_id,product_id,capacity_kg,lead_days,fill_rate,fixed_delivery,variable_delivery_per_kg,handling_cost,coordinated_trips,coordinated_distance_km,evidence_type,evidence_note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',vals)
            new_id=cur.lastrowid
            cur.executemany('INSERT INTO price_tiers (offer_id,min_quantity_kg,price_per_kg) VALUES (%s,%s,%s)',[(new_id,*r) for r in rows])
    return jsonify(id=new_id,message='Offer and price tiers saved'),201

@app.get('/api/decisions')
@require_login
def api_decisions():
    batches, proposed_totals, planning = decision_results(
        optimised=request.args.get('grouping') == 'optimised',
    )
    return jsonify(
        items=batches,
        proposed_reservation_totals=[
            {"offer_id": offer_id, "window_id": window_id, "quantity_kg": format(quantity, "f")}
            for (offer_id, window_id), quantity in sorted(proposed_totals.items())
        ],
        **planning,
    )

@app.get('/api/decisions/comparison')
@require_login
def api_decision_comparison():
    summary, _, _ = comparison_results()
    return jsonify(summary)


@app.get('/api/kpis')
@require_login
def api_kpis(): return jsonify(dashboard_metrics())

@app.post('/api/allocations')
@require_login
def api_allocate():
    d=body();offer_id=identifier(d,'offer_id');window_id=identifier(d,'window_id');qty=positive(d,'quantity_kg')
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT capacity_kg FROM supplier_offers WHERE id=%s AND active=1 FOR UPDATE',(offer_id,))
            offer=cur.fetchone()
            if not offer: return jsonify(error='Offer not found'),404
            cur.execute("SELECT COALESCE(SUM(quantity_kg),0) AS used FROM allocations WHERE offer_id=%s AND status='reserved'",(offer_id,))
            used=cur.fetchone()['used']
            if Decimal(str(used))+qty>Decimal(str(offer['capacity_kg'])): raise ValueError('Supplier capacity is already allocated')
            cur.execute('INSERT INTO allocations (offer_id,window_id,quantity_kg) VALUES (%s,%s,%s)',(offer_id,window_id,qty))
    return jsonify(message='Capacity reserved'),201

@app.post('/api/fulfilments')
@require_login
def api_fulfilment():
    d=body();oid=identifier(d,'demand_order_id'); delivered=nonnegative(d,'delivered_kg')
    vals=(oid,delivered,int(nonnegative(d,'planned_days')),int(nonnegative(d,'actual_days')),
          positive(d,'quoted_cost'),nonnegative(d,'actual_cost'))
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT quantity_kg,status FROM demand_orders WHERE id=%s FOR UPDATE',(oid,))
            order=cur.fetchone()
            if not order: return jsonify(error='Order not found'),404
            if order['status']!='committed': raise ValueError('Only committed orders can be fulfilled')
            if delivered>order['quantity_kg']: raise ValueError('Delivered quantity cannot exceed ordered quantity')
            cur.execute('INSERT INTO fulfilments (demand_order_id,delivered_kg,planned_days,actual_days,quoted_cost,actual_cost) VALUES (%s,%s,%s,%s,%s,%s)',vals)
            cur.execute("UPDATE demand_orders SET status='fulfilled' WHERE id=%s",(oid,))
    return jsonify(message='Fulfilment saved'),201

@app.errorhandler(ValueError)
def invalid(exc): return jsonify(error=str(exc)),400

@app.errorhandler(IntegrityError)
def integrity(exc):
    app.logger.warning('Database constraint rejected input: %s',type(exc).__name__)
    return jsonify(error='Duplicate or invalid related record; check existing IDs and unique constraints'),409

@app.errorhandler(404)
def not_found(exc): return jsonify(error='Route not found'),404

@app.errorhandler(Exception)
def server_error(exc):
    app.logger.exception('Unhandled request failure')
    return jsonify(error='Internal server error; see server logs'),500

if __name__=='__main__':
    if not app.secret_key or not os.getenv('APP_PASSWORD'):
        raise RuntimeError('Set SECRET_KEY and APP_PASSWORD in .env')
    app.run(debug=False)
