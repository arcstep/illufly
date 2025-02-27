(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[652,792],{1226:()=>{},3189:(e,t,n)=>{Promise.resolve().then(n.bind(n,3893))},3893:(e,t,n)=>{"use strict";n.r(t),n.d(t,{default:()=>a});var r=n(5155),l=n(2115),o=n(8435),s=n(9093);function a(){let{user:e,logout:t,fetchUser:n,refreshToken:a}=(0,o.A)(),[i,c]=(0,l.useState)(null);return e?i?(0,r.jsxs)("div",{className:"flex-1 p-4",children:[(0,r.jsxs)("div",{className:"text-red-500",children:["错误: ",i]}),(0,r.jsx)("button",{onClick:loadFiles,className:"mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600",children:"重试"})]}):(0,r.jsxs)("div",{className:"p-5 pt-12 h-screen flex flex-col",children:[(0,r.jsx)(s.A,{username:e.username,onLogout:t,onFetchUser:n,onRefreshToken:a,currentPath:"/agent"}),(0,r.jsx)("div",{className:"flex-1 overflow-y-auto min-h-[150px] p-4"})]}):null}},9093:(e,t,n)=>{"use strict";n.d(t,{A:()=>a});var r=n(5155),l=n(7396),o=n(2115);function s(e){let{username:t,onLogout:n}=e,[l,s]=(0,o.useState)(!1),[a,i]=(0,o.useState)(""),c=(0,o.useRef)(null);return(0,o.useEffect)(()=>{t?i(t.length>10?"".concat(t.slice(0,10),"..."):t):i("未登录")},[t]),(0,o.useEffect)(()=>{let e=e=>{c.current&&!c.current.contains(e.target)&&s(!1)};return document.addEventListener("mousedown",e),()=>{document.removeEventListener("mousedown",e)}},[]),(0,r.jsxs)("div",{className:"relative",ref:c,children:[(0,r.jsx)("button",{onClick:()=>s(!l),className:"bg-gray-700 text-white px-2 py-1 rounded hover:bg-gray-600",title:t,children:a}),l&&(0,r.jsxs)("div",{className:"absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded shadow-lg z-50",children:[(0,r.jsx)("hr",{className:"border-gray-600"}),(0,r.jsx)("button",{onClick:n,className:"w-full text-left px-4 py-2 text-red-500 hover:bg-gray-700",children:"退出"})]})]})}function a(e){let{username:t,onLogout:n,currentPath:o}=e;return(0,r.jsxs)("header",{className:"flex justify-between items-center fixed top-0 left-0 right-0 z-50 bg-gray-800 text-white p-2",children:[(0,r.jsx)("h1",{className:"text-xl md:text-2xl font-bold",children:"✨\uD83E\uDD8B ILLUFLY"}),(0,r.jsx)("div",{className:"flex space-x-4",children:["/chat","/knowledge","/favorite","/share"].map(e=>(0,r.jsx)(l.default,{href:e,children:(0,r.jsxs)("span",{className:"px-3 py-1 rounded-full transition-all duration-300 ".concat(o===e?"bg-gradient-to-r from-blue-400 to-purple-400 text-white shadow-md":"bg-transparent text-gray-200 hover:bg-gray-600"),children:["/chat"===e&&"对话","/knowledge"===e&&"知识","/favorite"===e&&"收藏","/share"===e&&"分享"]})},e))}),(0,r.jsx)("div",{className:"flex items-center",children:(0,r.jsx)(s,{username:t,onLogout:n})})]})}},8435:(e,t,n)=>{"use strict";n.d(t,{A:()=>c,AuthProvider:()=>i});var r=n(5155),l=n(2115),o=n(6046),s=n(6828);let a=(0,l.createContext)({user_id:null,username:null,email:null,role:null,device_id:null,isAuthenticated:!1,currentPath:null,login:async()=>{throw Error("AuthProvider not found")},logout:async()=>{throw Error("AuthProvider not found")},refresh_token:async()=>{throw Error("AuthProvider not found")},changeCurrentPath:async()=>{throw Error("AuthProvider not found")}});function i(e){let{children:t}=e,n=(0,o.useRouter)(),i=(0,o.useSearchParams)(),c=(0,o.usePathname)(),[u,d]=(0,l.useState)(!0),h=["/login","/register","/forgot-password"],[g,f]=(0,l.useState)(null),[m,x]=(0,l.useState)(null),[p,v]=(0,l.useState)(null),[w,y]=(0,l.useState)(null),[b,j]=(0,l.useState)(null),[N,P]=(0,l.useState)(!1),[k,E]=(0,l.useState)(null);(0,l.useEffect)(()=>{if(h.includes(c)){d(!1);return}S()},[c]);let S=async()=>{let e="".concat(s.J,"/auth/profile");console.log("api_url >>> ",e);try{console.log("开始刷新 token"),d(!0);let t=await fetch(e,{method:"GET",headers:{Accept:"application/json","Content-Type":"application/json","Cache-Control":"no-cache",Pragma:"no-cache"},credentials:"include",signal:AbortSignal.timeout(8e3)}),r=t.headers.get("set-cookie");if(console.log("响应中的cookie头:",r?"存在":"不存在"),t.ok){let e=await t.json();f(e.user_id),x(e.device_id),v(e.username),y(e.email),j(e.role),P(!0)}else console.log("响应不成功，重定向到登录页"),P(!1),n.replace("/login")}catch(t){console.error("刷新 token 详细错误:",{error:t,message:t instanceof Error?t.message:"未知错误",api_url:e}),P(!1),n.replace("/login")}finally{d(!1)}},A=async(e,t)=>{console.log("login >>> ",e,t);let r=await fetch("".concat(s.J,"/auth/login"),{method:"POST",credentials:"include",headers:{accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({username:e,password:t})});if(!r.ok)throw Error((await r.json()).detail||"Login failed");let l=await r.json();console.log("POST auth/login >>> ",l),f(l.user_id),x(l.device_id),v(l.username),y(l.email),j(l.role),P(!0);let o=i.get("from")||"/chat";n.replace(o)},_=async()=>{await fetch("".concat(s.J,"/auth/logout"),{method:"POST",credentials:"include"}),f(null),v(null),y(null),j(null),P(!1),n.replace("/login")},C=async e=>{E(e)};return u&&!h.includes(c)?(0,r.jsx)("div",{children:"Loading..."}):(0,r.jsx)(a.Provider,{value:{user_id:g,device_id:m,username:p,email:w,role:b,isAuthenticated:N,login:A,logout:_,refresh_token:S,currentPath:k,changeCurrentPath:C},children:t})}function c(){let e=(0,l.useContext)(a);if(void 0===e)throw Error("useAuth must be used within an AuthProvider");return e}},6828:(e,t,n)=>{"use strict";n.d(t,{J:()=>l,t:()=>o});var r=n(5521);let l="/api",o=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),r.default.push("/login")}}},e=>{var t=t=>e(e.s=t);e.O(0,[779,299,563,420,804,256,19,694,269,889,432,592,331,271,30,173,473,376,358],()=>t(3189)),_N_E=e.O()}]);