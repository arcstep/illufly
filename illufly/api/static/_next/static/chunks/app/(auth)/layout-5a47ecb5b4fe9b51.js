(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[97,792],{41226:()=>{},44856:(e,t,o)=>{Promise.resolve().then(o.bind(o,68435))},68435:(e,t,o)=>{"use strict";o.d(t,{A:()=>u,AuthProvider:()=>i});var n=o(95155),l=o(12115),r=o(76046),a=o(86828);let s=(0,l.createContext)({user_id:null,username:null,email:null,role:null,device_id:null,isAuthenticated:!1,currentPath:null,login:async()=>{throw Error("AuthProvider not found")},logout:async()=>{throw Error("AuthProvider not found")},refresh_token:async()=>{throw Error("AuthProvider not found")},changeCurrentPath:async()=>{throw Error("AuthProvider not found")}});function i(e){let{children:t}=e,o=(0,r.useRouter)(),i=(0,r.useSearchParams)(),u=(0,r.usePathname)(),[c,d]=(0,l.useState)(!0),h=["/login","/register","/forgot-password"],[g,f]=(0,l.useState)(null),[p,m]=(0,l.useState)(null),[v,P]=(0,l.useState)(null),[w,y]=(0,l.useState)(null),[S,_]=(0,l.useState)(null),[A,E]=(0,l.useState)(!1),[j,k]=(0,l.useState)(null);(0,l.useEffect)(()=>{if(h.includes(u)){d(!1);return}C()},[u]);let C=async()=>{let e="".concat(a.J,"/auth/profile");console.log("api_url >>> ",e);try{console.log("开始刷新 token"),d(!0);let t=await fetch(e,{method:"GET",headers:{Accept:"application/json","Content-Type":"application/json","Cache-Control":"no-cache",Pragma:"no-cache"},credentials:"include",signal:AbortSignal.timeout(8e3)});if(t.ok){let e=await t.json();f(e.user_id),m(e.device_id),P(e.username),y(e.email),_(e.role),E(!0)}else console.log("响应不成功，重定向到登录页"),E(!1),o.replace("/login")}catch(t){console.error("刷新 token 详细错误:",{error:t,message:t instanceof Error?t.message:"未知错误",api_url:e}),E(!1),o.replace("/login")}finally{d(!1)}},b=async(e,t)=>{console.log("login >>> ",e,t);let n=await fetch("".concat(a.J,"/auth/login"),{method:"POST",credentials:"include",headers:{accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({username:e,password:t})});if(!n.ok)throw Error((await n.json()).detail||"Login failed");let l=await n.json();console.log("POST auth/login >>> ",l),f(l.user_id),m(l.device_id),P(l.username),y(l.email),_(l.role),E(!0);let r=i.get("from")||"/chat";o.replace(r)},O=async()=>{await fetch("".concat(a.J,"/auth/logout"),{method:"POST",credentials:"include"}),f(null),P(null),y(null),_(null),E(!1),o.replace("/login")},T=async e=>{k(e)};return c&&!h.includes(u)?(0,n.jsx)("div",{children:"Loading..."}):(0,n.jsx)(s.Provider,{value:{user_id:g,device_id:p,username:v,email:w,role:S,isAuthenticated:A,login:b,logout:O,refresh_token:C,currentPath:j,changeCurrentPath:T},children:t})}function u(){let e=(0,l.useContext)(s);if(void 0===e)throw Error("useAuth must be used within an AuthProvider");return e}},86828:(e,t,o)=>{"use strict";o.d(t,{J:()=>l,t:()=>r});var n=o(85521);let l="/api",r=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),n.default.push("/login")}}},e=>{var t=t=>e(e.s=t);e.O(0,[779,299,563,420,804,256,19,694,269,889,432,592,331,271,30,173,473,376,358],()=>t(44856)),_N_E=e.O()}]);