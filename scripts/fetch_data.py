import json,os,urllib.request
from datetime import date,timedelta
U={"m":"https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-market/","p":"https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/bond-primary/","f":"https://gapi-ext.innodealing.com/dm-mcp-service/publicapi/mcp/v1/money-market/"}
def q(s,n,x):
 a={"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":n,"arguments":{"params":x}}};h={"Content-Type":"application/json","Accept":"application/json, text/event-stream","x-app-key":os.environ["DM_APP_KEY"],"x-app-secret":os.environ["DM_APP_SECRET"]}
 r=urllib.request.urlopen(urllib.request.Request(U[s],data=json.dumps(a).encode(),headers=h),timeout=30).read().decode();lines=[v[6:].strip() for v in r.splitlines() if v.startswith("data: ") and v[6:].strip()];z=json.loads(lines[-1])["result"];return json.JSONDecoder().raw_decode(z["content"][0]["text"].lstrip())[0]["data"]
t=date.today();a=t-timedelta(days=6);rows=[];x=t-timedelta(days=89)
while x<=t:
 y=min(x+timedelta(days=29),t);rows+=q("m","bond_yield_curve",{"user_message":"国债10年收益率曲线","curve_name":"中债国债收益率曲线","curve_term_list":["10"],"curve_type":1,"data_source":18,"start_date":x.isoformat(),"end_date":y.isoformat()});x=y+timedelta(days=1)
c={r["valuation_date"]:r.get("yield") for r in rows if str(r.get("curve_term")) in ("10","10.0")};p=q("p","bond_primary_data",{"user_message":"近一周国债发行","start_date":a.isoformat(),"end_date":t.isoformat(),"bond_category":2,"limit":200});L=[r for r in p[0].get("list",[]) if r.get("bond_type_desc")=="国债"]
I=[]
for r in L[:8]:
 v=r.get("issue_yield");label="发行收益率"
 if v is None:v=r.get("comprehensive_yield");label="综合收益率"
 if v is None:v=r.get("weighted_rate");label="加权收益率"
 if v is None:v=r.get("marginal_rate");label="边际收益率"
 I.append({"date":r.get("subscribe_date"),"code":r.get("security_id"),"tenor":r.get("bond_issue_tenor"),"amount":(r.get("actu_issue_amount") or 0)/10000,"yield":v,"yield_label":label,"multiple":r.get("compliant_subscription_mult")})
g=q("f","fund_calendar",{"user_message":"近一周政府债缴款","start_date":a.isoformat(),"end_date":t.isoformat(),"data_category":4})
o={"as_of":t.isoformat(),"ten_year_yield_curve":[{"date":k,"yield":c[k]} for k in sorted(c)],"treasury_issues":I,"government_payments":[{"date":r.get("data_date"),"net":r.get("gov_net_payment")} for r in g]}
open("data.json","w").write(json.dumps(o,ensure_ascii=False))
