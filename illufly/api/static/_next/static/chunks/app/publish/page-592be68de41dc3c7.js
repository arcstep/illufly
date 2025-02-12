(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[792,878],{1226:()=>{},835:(e,t,r)=>{Promise.resolve().then(r.bind(r,7276))},7276:(e,t,r)=>{"use strict";r.r(t),r.d(t,{default:()=>o});var s=r(5155),a=r(2115),n=r(3201),l=r(5731);function o(){let{user:e,logout:t,fetchUser:r,refreshToken:o}=(0,n.A)(),[c,i]=(0,a.useState)(null);return e?c?(0,s.jsxs)("div",{className:"flex-1 p-4",children:[(0,s.jsxs)("div",{className:"text-red-500",children:["错误: ",c]}),(0,s.jsx)("button",{onClick:loadFiles,className:"mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600",children:"重试"})]}):(0,s.jsxs)("div",{className:"p-5 h-screen flex flex-col",children:[(0,s.jsx)("div",{className:"h-10"}),(0,s.jsx)(l.A,{username:e.username,onLogout:t,onFetchUser:r,onRefreshToken:o,currentPath:"/publish"}),(0,s.jsx)("div",{className:"flex-1 overflow-y-auto min-h-[150px] p-4"})]}):null}},5731:(e,t,r)=>{"use strict";r.d(t,{A:()=>o});var s=r(5155),a=r(7396),n=r(2115);function l(e){let{username:t,onLogout:r,onFetchUser:a,onRefreshToken:l}=e,[o,c]=(0,n.useState)(!1),i=(0,n.useRef)(null),u=t.length>10?"".concat(t.slice(0,10),"..."):t;return(0,n.useEffect)(()=>{let e=e=>{i.current&&!i.current.contains(e.target)&&c(!1)};return document.addEventListener("mousedown",e),()=>{document.removeEventListener("mousedown",e)}},[]),(0,s.jsxs)("div",{className:"relative",ref:i,children:[(0,s.jsx)("button",{onClick:()=>c(!o),className:"bg-gray-700 text-white px-2 py-1 rounded hover:bg-gray-600",title:t,children:u}),o&&(0,s.jsxs)("div",{className:"absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded shadow-lg z-50",children:[(0,s.jsx)("button",{onClick:a,className:"w-full text-left px-4 py-2 text-white hover:bg-gray-700",children:"魔法师信息"}),(0,s.jsx)("button",{onClick:l,className:"w-full text-left px-4 py-2 text-white hover:bg-gray-700",children:"更新魔法令牌"}),(0,s.jsx)("hr",{className:"border-gray-600"}),(0,s.jsx)("button",{onClick:r,className:"w-full text-left px-4 py-2 text-red-500 hover:bg-gray-700",children:"离开梦幻岛"})]})]})}function o(e){let{username:t,onLogout:r,onFetchUser:n,onRefreshToken:o,currentPath:c}=e;return(0,s.jsxs)("header",{className:"flex justify-between items-center fixed top-0 left-0 right-0 z-50 bg-gray-800 text-white p-2",children:[(0,s.jsx)("h1",{className:"text-xl md:text-2xl font-bold",children:"✨\uD83E\uDD8B 梦幻岛"}),(0,s.jsx)("div",{className:"flex space-x-4",children:["/publish","/chat","/knowledge","/agent"].map(e=>(0,s.jsx)(a.default,{href:e,children:(0,s.jsxs)("span",{className:"px-3 py-1 rounded-full transition-all duration-300 ".concat(c===e?"bg-gradient-to-r from-blue-400 to-purple-400 text-white shadow-md":"bg-transparent text-gray-200 hover:bg-gray-600"),children:["/publish"===e&&"传说","/knowledge"===e&&"秘典","/agent"===e&&"精灵","/chat"===e&&"魔语"]})},e))}),(0,s.jsx)("div",{className:"flex items-center",children:(0,s.jsx)(l,{username:t,onLogout:r,onFetchUser:n,onRefreshToken:o})})]})}},3201:(e,t,r)=>{"use strict";r.d(t,{A:()=>i,O:()=>c});var s=r(5155),a=r(6046),n=r(2115),l=r(2492);let o=(0,n.createContext)(),c=e=>{let{children:t}=e,[r,c]=(0,n.useState)(null),[i,u]=(0,n.useState)(!0),h=(0,a.useRouter)(),d=(0,a.usePathname)();(0,n.useEffect)(()=>{(async()=>{if("/login"===d){u(!1);return}try{let e=await (0,l.im)();e.username?c(e):h.push("/login")}catch(e){c(null),h.push("/login")}finally{u(!1)}})()},[d]);let p=async(e,t)=>{try{let r=await (0,l.iD)(e,t);return r&&c(r),r}catch(e){throw console.error("登录失败:",e),e}},x=async()=>{try{c(null),await (0,l.ri)()}catch(e){console.error("登出错误:",e)}h.push("/login")},g=async()=>{try{await (0,l.Be)()}catch(e){console.error("刷新令牌错误:",e)}},f=async()=>{try{let e=await (0,l.im)();c(e)}catch(e){console.error("获取用户信息错误:",e)}};return(0,s.jsx)(o.Provider,{value:{user:r,loading:i,login:p,logout:x,refreshToken:g,fetchUser:f},children:t})},i=()=>(0,n.useContext)(o)},5370:(e,t,r)=>{"use strict";r.d(t,{A:()=>l});var s=r(2651),a=r(6828);let n=s.A.create({baseURL:a.J,withCredentials:!0});n.interceptors.response.use(e=>e,async e=>{let t=e.config;if(e.response&&401===e.response.status&&!t._retry){t._retry=!0;try{return await n.post("/api/auth/refresh-token",{},{withCredentials:!0}),n(t)}catch(e){return(0,a.t)(e),Promise.reject(e)}}return e.response&&403===e.response.status&&console.error("访问被拒绝:",e),(0,a.t)(e),Promise.reject(e)});let l=n},2492:(e,t,r)=>{"use strict";r.d(t,{Be:()=>o,iD:()=>a,im:()=>l,ri:()=>n});var s=r(5370);let a=async(e,t)=>{try{let r=new URLSearchParams;r.append("grant_type","password"),r.append("username",e),r.append("password",t);let a=await s.A.post("/api/auth/login",r,{withCredentials:!0,headers:{"Content-Type":"application/x-www-form-urlencoded"}});if(!a.request.withCredentials)return alert("请检查浏览器隐私设置：客户端无法保存 Cookie 导致登录失败！"),null;return a.data}catch(e){throw console.error("登录失败:",e.response?e.response.data:e.message),Error("登录失败，请检查您的凭据并重试。")}},n=async()=>{try{await s.A.post("/api/auth/logout",{},{withCredentials:!0})}catch(e){if(e.response&&401===e.response.status)return;throw Error("登出失败")}},l=async()=>{try{return(await s.A.get("/api/auth/profile")).data}catch(e){console.log("获取用户信息失败")}},o=async()=>{try{await s.A.post("/api/auth/refresh-token",{},{withCredentials:!0})}catch(e){console.log("刷新令牌失败")}}},6828:(e,t,r)=>{"use strict";r.d(t,{J:()=>a,t:()=>n});var s=r(5521);let a="http://localhost:8001",n=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),s.default.push("/login")}}},e=>{var t=t=>e(e.s=t);e.O(0,[779,420,804,19,622,694,432,592,331,271,30,519,408,473,376,358],()=>t(835)),_N_E=e.O()}]);