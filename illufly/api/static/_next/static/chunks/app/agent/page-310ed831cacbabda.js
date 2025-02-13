(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[652,792],{1226:()=>{},3189:(e,t,l)=>{Promise.resolve().then(l.bind(l,3893))},3893:(e,t,l)=>{"use strict";l.r(t),l.d(t,{default:()=>o});var n=l(5155),r=l(2115),s=l(8435),a=l(9093);function o(){let{user:e,logout:t,fetchUser:l,refreshToken:o}=(0,s.A)(),[i,u]=(0,r.useState)(null);return e?i?(0,n.jsxs)("div",{className:"flex-1 p-4",children:[(0,n.jsxs)("div",{className:"text-red-500",children:["错误: ",i]}),(0,n.jsx)("button",{onClick:loadFiles,className:"mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600",children:"重试"})]}):(0,n.jsxs)("div",{className:"p-5 pt-12 h-screen flex flex-col",children:[(0,n.jsx)(a.A,{username:e.username,onLogout:t,onFetchUser:l,onRefreshToken:o,currentPath:"/agent"}),(0,n.jsx)("div",{className:"flex-1 overflow-y-auto min-h-[150px] p-4"})]}):null}},9093:(e,t,l)=>{"use strict";l.d(t,{A:()=>o});var n=l(5155),r=l(7396),s=l(2115);function a(e){let{username:t,onLogout:l,onFetchUser:r,onRefreshToken:a}=e,[o,i]=(0,s.useState)(!1),u=(0,s.useRef)(null),c="未登录";return t&&(c=t.length>10?"".concat(t.slice(0,10),"..."):t),(0,s.useEffect)(()=>{let e=e=>{u.current&&!u.current.contains(e.target)&&i(!1)};return document.addEventListener("mousedown",e),()=>{document.removeEventListener("mousedown",e)}},[]),(0,n.jsxs)("div",{className:"relative",ref:u,children:[(0,n.jsx)("button",{onClick:()=>i(!o),className:"bg-gray-700 text-white px-2 py-1 rounded hover:bg-gray-600",title:t,children:c}),o&&(0,n.jsxs)("div",{className:"absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded shadow-lg z-50",children:[(0,n.jsx)("button",{onClick:r,className:"w-full text-left px-4 py-2 text-white hover:bg-gray-700",children:"魔法师信息"}),(0,n.jsx)("button",{onClick:a,className:"w-full text-left px-4 py-2 text-white hover:bg-gray-700",children:"更新魔法令牌"}),(0,n.jsx)("hr",{className:"border-gray-600"}),(0,n.jsx)("button",{onClick:l,className:"w-full text-left px-4 py-2 text-red-500 hover:bg-gray-700",children:"离开梦幻岛"})]})]})}function o(e){let{username:t,onLogout:l,onFetchUser:s,onRefreshToken:o,currentPath:i}=e;return(0,n.jsxs)("header",{className:"flex justify-between items-center fixed top-0 left-0 right-0 z-50 bg-gray-800 text-white p-2",children:[(0,n.jsx)("h1",{className:"text-xl md:text-2xl font-bold",children:"✨\uD83E\uDD8B 梦幻岛"}),(0,n.jsx)("div",{className:"flex space-x-4",children:["/publish","/chat","/knowledge","/agent"].map(e=>(0,n.jsx)(r.default,{href:e,children:(0,n.jsxs)("span",{className:"px-3 py-1 rounded-full transition-all duration-300 ".concat(i===e?"bg-gradient-to-r from-blue-400 to-purple-400 text-white shadow-md":"bg-transparent text-gray-200 hover:bg-gray-600"),children:["/publish"===e&&"传说","/knowledge"===e&&"秘典","/agent"===e&&"精灵","/chat"===e&&"魔语"]})},e))}),(0,n.jsx)("div",{className:"flex items-center",children:(0,n.jsx)(a,{username:t,onLogout:l,onFetchUser:s,onRefreshToken:o})})]})}},8435:(e,t,l)=>{"use strict";l.d(t,{A:()=>u,AuthProvider:()=>i});var n=l(5155),r=l(2115),s=l(6046),a=l(6828);let o=(0,r.createContext)({user_id:null,username:null,email:null,role:null,device_id:null,isAuthenticated:!1,login:async()=>{throw Error("AuthProvider not found")},logout:async()=>{throw Error("AuthProvider not found")},refresh_token:async()=>{throw Error("AuthProvider not found")}});function i(e){let{children:t}=e,l=(0,s.useRouter)(),i=(0,s.useSearchParams)(),u=(0,s.usePathname)(),c=["/login","/register","/forgot-password"],[d,h]=(0,r.useState)(null),[x,f]=(0,r.useState)(null),[g,m]=(0,r.useState)(null),[p,v]=(0,r.useState)(null),[b,w]=(0,r.useState)(null),[y,j]=(0,r.useState)(!1);(0,r.useEffect)(()=>{c.includes(u)||N()},[u]);let N=async()=>{let e=await fetch("".concat(a.J,"/auth/profile"),{credentials:"include"});if(e.ok){let t=await e.json();console.log(t),h(t.user_id),f(t.device_id),m(t.username),v(t.email),w(t.role),j(!0)}else l.push("/login")},_=async(e,t)=>{console.log("login >>> ",e,t);let n=await fetch("".concat(a.J,"/auth/login"),{method:"POST",credentials:"include",headers:{accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({username:e,password:t})});if(!n.ok)throw Error((await n.json()).detail||"Login failed");let r=await n.json();h(r.user_id),f(r.device_id),m(r.username),v(r.email),w(r.role),j(!0);let s=i.get("from")||"/";l.replace(s)},k=async()=>{await fetch("".concat(a.J,"/auth/logout"),{method:"POST",credentials:"include"}),h(null),m(null),v(null),w(null),j(!1),l.replace("/login")};return(0,n.jsx)(o.Provider,{value:{user_id:d,device_id:x,username:g,email:p,role:b,isAuthenticated:y,login:_,logout:k,refresh_token:N},children:t})}function u(){let e=(0,r.useContext)(o);if(void 0===e)throw Error("useAuth must be used within an AuthProvider");return e}},6828:(e,t,l)=>{"use strict";l.d(t,{J:()=>r,t:()=>s});var n=l(5521);let r=l(2818).env.NEXT_PUBLIC_API_BASE_URL||"/api",s=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),n.default.push("/login")}}},e=>{var t=t=>e(e.s=t);e.O(0,[779,420,804,19,622,694,432,592,331,271,30,519,408,473,376,358],()=>t(3189)),_N_E=e.O()}]);