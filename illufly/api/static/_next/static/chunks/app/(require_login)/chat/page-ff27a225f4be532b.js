(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[508,792],{41226:()=>{},84615:(e,t,s)=>{Promise.resolve().then(s.bind(s,39473))},39473:(e,t,s)=>{"use strict";s.r(t),s.d(t,{default:()=>w});var a=s(95155),r=s(12115),n=s(86828),l=s(69329);let o=(0,r.createContext)({currentThreadId:null,threads:[],lastChunks:[],messages:[],createNewThread:async()=>{throw Error("ChatProvider not found")},loadAllThreads:async()=>{throw Error("ChatProvider not found")},ask:async()=>{throw Error("ChatProvider not found")},toggleFavorite:async()=>{throw Error("ChatProvider not found")},switchThread:async()=>{throw Error("ChatProvider not found")}});function i(e){let{children:t}=e,[s,i]=(0,r.useState)(null),[c,d]=(0,r.useState)([]),[u,h]=(0,r.useState)([]),[m,x]=(0,r.useState)([]),[g,f]=(0,r.useState)([]),p=(0,r.useRef)(new Map);(0,r.useEffect)(()=>{g.length>0&&(x(e=>[...e,...g]),f([]))},[g]);let y=e=>{if(0===e.length)return[];let t=new Map;return e.forEach(e=>{var s;t.has(e.message_id)||t.set(e.message_id,[]),null===(s=t.get(e.message_id))||void 0===s||s.push(e)}),Array.from(t.entries()).filter(e=>{let[t]=e;return!p.current.has(t)}).map(e=>{let[t,s]=e;p.current.set(t,s[0]);let a=s[0];return 1===s.length?a:{...a,text:s.map(e=>e.text).join(""),message_type:"text"}})},w=(0,r.useMemo)(()=>{if(!s&&0===u.length)return[];let e=[...m,...y(u)],t=new Map;return e.forEach(e=>{let s=e.message_id.replace(/^temp_/,"");(!t.has(s)||e.completed_at>t.get(s).completed_at)&&t.set(s,e)}),Array.from(t.values()).sort((e,t)=>e.completed_at-t.completed_at)},[m,u,s]),b=async()=>{let e=await fetch("".concat(n.J,"/chat/threads"),{method:"POST",credentials:"include"}),t=await e.json();return i(t.thread_id),d([...c,t]),x([]),h([]),await v(),t.thread_id},j=async e=>{if(c.map(e=>e.thread_id).includes(e)){i(e);let t=await fetch("".concat(n.J,"/chat/thread/").concat(e,"/messages"),{credentials:"include"}),s=await t.json();console.log("加载远程对话消息数据",s),x(s||[])}},v=async()=>{try{let e=await fetch("".concat(n.J,"/chat/threads"),{credentials:"include"}),t=await e.json();d(t),console.log("收到的线程数据:",t)}catch(e){throw console.error("加载线程失败:",e),e}},N=async e=>{if(!s)return;h([]);let t=new AbortController,a=()=>{h(e=>{let t=new Map;return e.forEach(e=>{var s;t.has(e.message_id)||t.set(e.message_id,[]),null===(s=t.get(e.message_id))||void 0===s||s.push(e)}),t.forEach((e,t)=>{let s={...e[0],text:e.map(e=>e.text).join(""),message_type:"text"};x(e=>[...e.filter(e=>e.message_id!=="temp_".concat(t)),{...s,message_type:"text"}]),p.current.delete(t)}),[]})};try{await (0,l.y)("".concat(n.J,"/chat/complete"),{method:"POST",credentials:"include",headers:{accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({imitator:"QWEN",model:"qwen-plus",thread_id:s,messages:[{role:"user",content:e}]}),signal:t.signal,onopen:async e=>{if(200!==e.status||!e.ok)throw Error("请求失败: ".concat(e.status));if(!e.body)throw Error("没有响应体")},onmessage(e){try{if(console.log("收到消息:",e.data),"[DONE]"===e.data){a();return}let t=JSON.parse(e.data);"text_chunk"===t.message_type?(console.log("收到文本块:",t),h(e=>[...e,t]),_(t)):"text"===t.message_type&&(console.log("收到完整消息:",t),a(),f(e=>[...e,t]))}catch(e){console.error("解析消息失败:",e)}},onclose(){console.log("SSE 连接已关闭"),a()},onerror(e){throw console.error("SSE 错误:",e),e}})}catch(e){throw console.error("发送消息失败:",e),e}finally{t.abort()}},_=e=>{let t=e.message_id;if(p.current.has(t)){let s=p.current.get(t);p.current.set(t,{...s,text:s.text+e.text,completed_at:e.completed_at})}else p.current.set(t,{...e,message_type:"text",text:e.text});x(e=>[...e.filter(e=>e.message_id!=="temp_".concat(t)),{...p.current.get(t),message_id:"temp_".concat(t)}])},S=async e=>{(await fetch("".concat(n.J,"/chat/messages/").concat(e,"/favorite"),{method:"POST",credentials:"include"})).ok};return(0,a.jsx)(o.Provider,{value:{currentThreadId:s,threads:c,lastChunks:u,messages:w,createNewThread:b,switchThread:j,loadAllThreads:v,ask:N,toggleFavorite:S},children:t})}function c(){let e=(0,r.useContext)(o);if(void 0===e)throw Error("useChat must be used within a ChatProvider");return e}function d(){let{threads:e,loadAllThreads:t,switchThread:s,createNewThread:n,currentThreadId:l}=c(),[o,i]=(0,r.useState)(!1);return(0,r.useEffect)(()=>{(async()=>{i(!0);try{await t(),console.log("更新 threads: ",e)}catch(e){console.error("加载历史记录失败:",e)}finally{i(!1)}})()},[]),(0,a.jsxs)("div",{className:"w-full max-w-xs p-4 border-b md:border-b-0 md:border-r",children:[(0,a.jsx)("button",{className:"w-full p-3 mb-4 text-left text-white bg-blue-500 rounded-lg shadow-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:ring-opacity-50 transition duration-150 ease-in-out",onClick:n,children:(0,a.jsx)("span",{className:"font-medium",children:"+ 新对话"})}),o?(0,a.jsx)("div",{children:"加载中..."}):e.map(e=>{let{thread_id:t,title:r}=e;return(0,a.jsx)("div",{className:"border-b border-gray-200 ".concat(t===l?"border-l-2 border-l-red-500":""),children:(0,a.jsx)("button",{onClick:()=>s(t),className:"w-full p-2 text-left hover:bg-gray-100",children:(0,a.jsx)("div",{className:"font-medium",children:r||"新对话"})},t)},t)})]})}var u=s(9757),h=s(95055),m=s(18050),x=s(86084);function g(){let{threads:e,switchThread:t,currentThreadId:s,messages:n}=c(),l=(0,r.useRef)(null),[o,i]=(0,r.useState)([]),[d,g]=(0,r.useState)({}),f={user:"\uD83E\uDDD1‍\uD83D\uDCBC",assistant:"\uD83E\uDD16",system:"❤️",tool:"\uD83D\uDD27"};(0,r.useEffect)(()=>{let s=e.sort((e,t)=>t.created_at-e.created_at)[0];s&&t(s.thread_id)},[e]),(0,r.useEffect)(()=>{var e;null===(e=l.current)||void 0===e||e.scrollIntoView({behavior:"smooth"})},[n]);let p=e=>{i(t=>t.includes(e)?t.filter(t=>t!==e):[...t,e])};return(0,a.jsxs)("div",{className:"h-full flex flex-col bg-gray-50",children:[(0,a.jsx)("div",{className:"flex-1 overflow-y-auto p-4",children:(0,a.jsxs)("ul",{className:"space-y-4",children:[n.map(e=>(0,a.jsxs)("li",{className:"flex gap-3 group relative p-4 rounded-lg shadow-sm bg-white \n                                ".concat(o.includes(e.message_id)?"border-2 border-blue-500":"border border-gray-200"),children:[(0,a.jsx)("div",{className:"w-8 flex-shrink-0",children:(0,a.jsx)("button",{className:"cursor-pointer w-6 h-6 rounded-full flex items-center justify-center \n                                        ".concat(o.includes(e.message_id)?"bg-blue-500 text-white":"bg-gray-200 text-gray-400 opacity-0 group-hover:opacity-100"," \n                                        transition-opacity duration-200"),onClick:()=>p(e.message_id),title:"选择消息",children:(0,a.jsx)(u.g,{icon:h.e68,className:"text-sm"})})}),(0,a.jsxs)("div",{className:"flex-1 min-w-0",children:[(0,a.jsxs)("div",{className:"flex items-center gap-2 mb-2",children:[(0,a.jsx)("span",{className:"font-medium text-gray-700",children:f[e.role]+" "+e.service_name}),(0,a.jsx)("span",{className:"inline-block bg-blue-100 text-blue-800 text-xs rounded-full px-2 py-0.5",children:e.message_type.toUpperCase()}),e.favorite&&(0,a.jsx)("span",{className:"text-yellow-500",children:(0,a.jsx)(u.g,{icon:h.yy,className:"text-sm"})}),(0,a.jsx)(x.A,{content:e.text}),(0,a.jsx)("span",{className:"text-xs text-gray-400 ml-auto",children:new Date(1e3*e.completed_at).toLocaleString()})]}),(0,a.jsx)("div",{className:"text-gray-800",children:(0,a.jsx)(m.A,{content:e.text,className:"prose prose-sm max-w-none"})})]})]},e.message_id)),(0,a.jsx)("div",{ref:l})]})}),o.length>0&&(0,a.jsxs)("div",{className:"sticky bottom-0 bg-white p-3 shadow-md flex justify-end gap-4",children:[(0,a.jsx)("button",{className:"px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700",onClick:()=>{console.log("分享消息:",n.filter(e=>o.includes(e.id)))},children:"分享选中消息"}),(0,a.jsx)("button",{className:"px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-700",onClick:()=>{i([])},children:"取消选择"})]})]})}function f(){let{ask:e}=c(),[t,s]=(0,r.useState)(""),[n,l]=(0,r.useState)([]),o=e=>{l(t=>t.filter(t=>t.name!==e))};return(0,a.jsx)("div",{className:"sticky bottom-0 bg-gray-100 p-1 rounded-lg shadow-inner",children:(0,a.jsxs)("div",{className:"flex flex-col bg-white p-2 rounded-lg shadow-md",children:[n.length>0&&(0,a.jsx)("div",{className:"flex flex-wrap mb-2",children:n.map((e,t)=>(0,a.jsxs)("div",{className:"flex items-center text-sm text-gray-600 mr-2 mb-1",children:[(0,a.jsx)("span",{className:"mr-1",children:e.name}),(0,a.jsx)("button",{className:"text-red-500 hover:text-red-600",onClick:()=>o(e.name),children:(0,a.jsx)(u.g,{icon:h.GRI})})]},t))}),(0,a.jsxs)("div",{className:"flex items-center",children:[(0,a.jsxs)("label",{className:"flex items-center cursor-pointer text-blue-500 hover:text-blue-600 mr-2",children:[(0,a.jsx)(u.g,{icon:h.WMI}),(0,a.jsx)("input",{type:"file",className:"hidden",multiple:!0,onChange:e=>{let t=Array.from(e.target.files);l(e=>[...e,...t])}})]}),(0,a.jsx)("textarea",{className:"flex-1 p-3 m-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-blue-300 transition duration-150 ease-in-out",rows:"1",style:{maxHeight:"10em",resize:"none",overflowY:"auto"},placeholder:"输入你的消息...",value:t,onChange:e=>s(e.target.value),onKeyDown:a=>{"Enter"===a.key&&!a.shiftKey&&(a.preventDefault(),t.trim()&&(e(t),s(""),a.target.style.height="auto"))},onInput:e=>{let t=e.target;t.style.height="auto",t.style.height="".concat(Math.min(t.scrollHeight,160),"px")}}),(0,a.jsx)("button",{className:"bg-blue-400 text-white px-4 py-2 ml-2 rounded-lg shadow-md hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:ring-opacity-50 transition duration-150 ease-in-out",onClick:e=>{t.trim()&&(onSendMessage(t),s(""),e.target.previousSibling.style.height="auto")},children:"发送"})]})]})})}var p=s(68435);function y(){let{isAuthenticated:e,changeCurrentPath:t}=(0,p.A)(),[s]=(0,r.useState)(!0);return((0,r.useEffect)(()=>{t("/chat")},[]),e)?(0,a.jsxs)("div",{className:"flex flex-1 flex-col md:flex-row h-full",children:[s&&(0,a.jsx)("div",{className:"w-full md:w-1/4 h-full flex flex-col",children:(0,a.jsx)("div",{className:"flex-1 overflow-y-auto",children:(0,a.jsx)(d,{})})}),(0,a.jsxs)("div",{className:"flex-1 flex flex-col h-full",children:[(0,a.jsx)("div",{className:"flex-1 overflow-y-auto p-4 h-full",children:(0,a.jsx)(g,{})}),(0,a.jsx)(f,{})]})]}):(0,a.jsx)("div",{children:"Loading..."})}function w(){return(0,a.jsx)(r.Suspense,{fallback:(0,a.jsx)("div",{children:"Chat Loading..."}),children:(0,a.jsx)(i,{children:(0,a.jsx)(y,{})})})}},86084:(e,t,s)=>{"use strict";s.d(t,{A:()=>o});var a=s(95155),r=s(12115),n=s(9757),l=s(95055);function o(e){let{content:t,getContent:s}=e,[o,i]=(0,r.useState)({show:!1,position:{x:0,y:0}}),[c,d]=(0,r.useState)(!1),u=async e=>{let a=t;if("function"==typeof s&&!t){d(!0);try{a=await s()}catch(e){console.error("获取复制内容失败:",e);return}finally{d(!1)}}navigator.clipboard.writeText(a).then(()=>{i({show:!0,position:{x:e.clientX,y:e.clientY}}),setTimeout(()=>i({show:!1,position:{x:0,y:0}}),500)}).catch(e=>{console.error("复制失败:",e)})};return(0,a.jsxs)(a.Fragment,{children:[(0,a.jsx)("button",{className:"ml-2 text-gray-400 hover:text-gray-600 focus:text-gray-800 transition-colors duration-200",onClick:u,title:"复制内容",disabled:c,children:(0,a.jsx)(n.g,{icon:c?l.z1G:l.jPR,className:c?"animate-spin":""})}),o.show&&(0,a.jsx)("div",{className:"absolute bg-green-500 text-white px-2 py-1 rounded shadow-lg",style:{top:o.position.y-30,left:o.position.x,zIndex:200},children:"复制成功"})]})}},18050:(e,t,s)=>{"use strict";s.d(t,{A:()=>g});var a=s(95155);s(12115);var r=s(87564),n=s(77558),l=s(69054),o=s(27802),i=s(26731),c=s(77076),d=s(44264),u=s(38629),h=s(43273),m=s(24920);let x={...h.j,tagNames:[...h.j.tagNames,"question","final_answer","no_final_answer","context","knowledge","OUTLINE"],attributes:{...h.j.attributes,question:["className"],final_answer:["className"],no_final_answer:["className"],context:["className"],knowledge:["className"],OUTLINE:["className"]}};function g(e){let{content:t,className:s=""}=e,h=e=>{let{tagName:t,...s}=e;return(0,a.jsxs)("div",{className:"relative border border-blue-300 p-4 my-4 rounded-md bg-blue-50",children:[(0,a.jsx)("span",{className:"absolute top-0 left-2 bg-white px-2 text-xs text-blue-500 border border-blue-300 rounded -mt-2.5",children:t}),(0,a.jsx)("div",{...s})]})};return(0,a.jsx)("div",{className:"prose prose-sm max-w-none ".concat(s," bg-gray-100 p-2 rounded-lg shadow-md"),children:(0,a.jsx)(r.o,{remarkPlugins:[n.A,l.A,c.A,d.A],rehypePlugins:[u.A,(0,m.A)(x),o.A,i.A],components:{question:e=>(0,a.jsx)(h,{tagName:"question",...e}),final_answer:e=>(0,a.jsx)(h,{tagName:"final_answer",...e}),no_final_answer:e=>(0,a.jsx)(h,{tagName:"no_final_answer",...e}),context:e=>(0,a.jsx)(h,{tagName:"context",...e}),knowledge:e=>(0,a.jsx)(h,{tagName:"knowledge",...e}),OUTLINE:e=>(0,a.jsx)(h,{tagName:"OUTLINE",...e}),h1:e=>{let{node:t,...s}=e;return(0,a.jsx)("h1",{className:"text-3xl font-bold my-4",...s})},h2:e=>{let{node:t,...s}=e;return(0,a.jsx)("h2",{className:"text-2xl font-semibold my-3",...s})},p:e=>{let{node:t,...s}=e;return(0,a.jsx)("p",{className:"text-base leading-relaxed my-2",...s})},pre:e=>{let{node:t,...s}=e;return(0,a.jsx)("pre",{className:"bg-gray-800 text-white p-4 rounded-md my-4 overflow-x-auto",...s})}},children:t||""})})}},68435:(e,t,s)=>{"use strict";s.d(t,{A:()=>c,AuthProvider:()=>i});var a=s(95155),r=s(12115),n=s(76046),l=s(86828);let o=(0,r.createContext)({user_id:null,username:null,email:null,role:null,device_id:null,isAuthenticated:!1,currentPath:null,login:async()=>{throw Error("AuthProvider not found")},logout:async()=>{throw Error("AuthProvider not found")},refresh_token:async()=>{throw Error("AuthProvider not found")},changeCurrentPath:async()=>{throw Error("AuthProvider not found")}});function i(e){let{children:t}=e,s=(0,n.useRouter)(),i=(0,n.useSearchParams)(),c=(0,n.usePathname)(),[d,u]=(0,r.useState)(!0),h=["/login","/register","/forgot-password"],[m,x]=(0,r.useState)(null),[g,f]=(0,r.useState)(null),[p,y]=(0,r.useState)(null),[w,b]=(0,r.useState)(null),[j,v]=(0,r.useState)(null),[N,_]=(0,r.useState)(!1),[S,E]=(0,r.useState)(null);(0,r.useEffect)(()=>{if(h.includes(c)){u(!1);return}k()},[c]);let k=async()=>{let e="".concat(l.J,"/auth/profile");console.log("api_url >>> ",e);try{console.log("开始刷新 token"),u(!0);let t=await fetch(e,{method:"GET",headers:{Accept:"application/json","Content-Type":"application/json","Cache-Control":"no-cache",Pragma:"no-cache"},credentials:"include",signal:AbortSignal.timeout(8e3)});if(t.ok){let e=await t.json();x(e.user_id),f(e.device_id),y(e.username),b(e.email),v(e.role),_(!0)}else console.log("响应不成功，重定向到登录页"),_(!1),s.replace("/login")}catch(t){console.error("刷新 token 详细错误:",{error:t,message:t instanceof Error?t.message:"未知错误",api_url:e}),_(!1),s.replace("/login")}finally{u(!1)}},C=async(e,t)=>{console.log("login >>> ",e,t);let a=await fetch("".concat(l.J,"/auth/login"),{method:"POST",credentials:"include",headers:{accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({username:e,password:t})});if(!a.ok)throw Error((await a.json()).detail||"Login failed");let r=await a.json();console.log("POST auth/login >>> ",r),x(r.user_id),f(r.device_id),y(r.username),b(r.email),v(r.role),_(!0);let n=i.get("from")||"/chat";s.replace(n)},A=async()=>{await fetch("".concat(l.J,"/auth/logout"),{method:"POST",credentials:"include"}),x(null),y(null),b(null),v(null),_(!1),s.replace("/login")},P=async e=>{E(e)};return d&&!h.includes(c)?(0,a.jsx)("div",{children:"Loading..."}):(0,a.jsx)(o.Provider,{value:{user_id:m,device_id:g,username:p,email:w,role:j,isAuthenticated:N,login:C,logout:A,refresh_token:k,currentPath:S,changeCurrentPath:P},children:t})}function c(){let e=(0,r.useContext)(o);if(void 0===e)throw Error("useAuth must be used within an AuthProvider");return e}},86828:(e,t,s)=>{"use strict";s.d(t,{J:()=>r,t:()=>n});var a=s(85521);let r="/api",n=e=>{e.response&&401===e.response.status?console.log("未授权，重定向到登录页"):console.log("API 请求错误:",e),a.default.push("/login")}}},e=>{var t=t=>e(e.s=t);e.O(0,[779,299,563,420,804,256,19,694,269,889,432,592,331,271,30,173,473,376,358],()=>t(84615)),_N_E=e.O()}]);