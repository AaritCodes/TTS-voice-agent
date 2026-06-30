"use client";

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  Phone, 
  Clock, 
  CheckCircle, 
  AlertCircle,
  LayoutDashboard,
  List,
  BarChart3,
  Settings,
  Mic,
  Activity
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

// --- MOCK DATA ---
const chartData = [
  { name: 'Mon', calls: 45 },
  { name: 'Tue', calls: 52 },
  { name: 'Wed', calls: 38 },
  { name: 'Thu', calls: 85 },
  { name: 'Fri', calls: 48 },
  { name: 'Sat', calls: 20 },
  { name: 'Sun', calls: 15 },
];

const recentCalls = [
  { id: 'CALL-1023', phone: '+1 (555) 019-2831', duration: '3m 42s', status: 'Success', intent: 'Technical Support', date: 'Just now' },
  { id: 'CALL-1022', phone: '+1 (555) 847-1922', duration: '1m 15s', status: 'Failed', intent: 'Unknown', date: '10 mins ago' },
  { id: 'CALL-1021', phone: '+1 (555) 332-9011', duration: '5m 02s', status: 'Success', intent: 'Billing Query', date: '1 hour ago' },
  { id: 'CALL-1020', phone: '+1 (555) 774-2099', duration: '2m 30s', status: 'Success', intent: 'Sales', date: '3 hours ago' },
];

// --- ANIMATION VARIANTS ---
const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.1 }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } }
};

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('dashboard');

  return (
    <div className="flex h-screen bg-[#0B0F19] text-slate-200 font-sans overflow-hidden selection:bg-cyan-500/30">
      
      {/* SIDEBAR (Glassmorphism) */}
      <motion.div 
        initial={{ x: -250 }}
        animate={{ x: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="w-64 bg-slate-900/40 backdrop-blur-xl border-r border-slate-800/60 flex flex-col relative z-20"
      >
        {/* Glow accent */}
        <div className="absolute top-0 left-0 w-full h-32 bg-cyan-500/10 blur-[50px] -z-10" />

        <div className="h-20 flex items-center px-6 border-b border-slate-800/60">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 shadow-[0_0_15px_rgba(6,182,212,0.5)] mr-3">
            <Mic className="w-5 h-5 text-white" />
          </div>
          <span className="text-xl font-bold tracking-tight text-white">
            Voice<span className="text-cyan-400">Agent</span>
          </span>
        </div>
        
        <nav className="flex-1 px-4 py-8 space-y-2">
          <NavItem icon={<LayoutDashboard />} label="Dashboard" active={activeTab === 'dashboard'} onClick={() => setActiveTab('dashboard')} />
          <NavItem icon={<List />} label="Call Logs" active={activeTab === 'logs'} onClick={() => setActiveTab('logs')} />
          <NavItem icon={<BarChart3 />} label="Analytics" active={activeTab === 'analytics'} onClick={() => setActiveTab('analytics')} />
          <NavItem icon={<Settings />} label="Settings" active={activeTab === 'settings'} onClick={() => setActiveTab('settings')} />
        </nav>
        
        <div className="p-4 border-t border-slate-800/60">
          <div className="flex items-center p-2 rounded-xl hover:bg-slate-800/50 transition-colors cursor-pointer">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-500 to-indigo-500 flex items-center justify-center text-white font-bold shadow-lg">
              A
            </div>
            <div className="ml-3">
              <p className="text-sm font-semibold text-slate-200">Arvind & Team</p>
              <p className="text-xs text-slate-400 flex items-center">
                <span className="w-2 h-2 rounded-full bg-green-500 mr-1.5 animate-pulse" />
                Online
              </p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* MAIN CONTENT */}
      <div className="flex-1 flex flex-col relative overflow-hidden">
        {/* Ambient background glows */}
        <div className="absolute top-[-20%] right-[-10%] w-[500px] h-[500px] rounded-full bg-indigo-600/10 blur-[120px] pointer-events-none" />
        <div className="absolute bottom-[-20%] left-[-10%] w-[600px] h-[600px] rounded-full bg-cyan-600/10 blur-[150px] pointer-events-none" />

        {/* HEADER */}
        <header className="h-20 bg-slate-900/20 backdrop-blur-md border-b border-slate-800/60 flex items-center justify-between px-8 z-10">
          <motion.h1 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-2xl font-semibold text-white tracking-tight flex items-center"
          >
            Overview
            <div className="ml-4 px-3 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 flex items-center">
              <Activity className="w-4 h-4 text-cyan-400 mr-2 animate-pulse" />
              <span className="text-xs font-medium text-cyan-400 uppercase tracking-wider">Live System Active</span>
            </div>
          </motion.h1>
          <motion.button 
            whileHover={{ scale: 1.05, boxShadow: "0 0 20px rgba(6,182,212,0.4)" }}
            whileTap={{ scale: 0.95 }}
            className="bg-gradient-to-r from-cyan-500 to-blue-600 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-lg flex items-center"
          >
            <Phone className="w-4 h-4 mr-2" />
            Make Test Call
          </motion.button>
        </header>

        {/* DASHBOARD CONTENT */}
        <main className="flex-1 overflow-y-auto p-8 z-10 scrollbar-hide">
          <motion.div 
            variants={containerVariants}
            initial="hidden"
            animate="show"
            className="max-w-7xl mx-auto"
          >
            {/* METRIC CARDS */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              <MetricCard 
                title="Total Calls Today" 
                value="124" 
                trend="+12%" 
                icon={<Phone className="w-6 h-6 text-cyan-400" />} 
                glowColor="rgba(6,182,212,0.5)"
              />
              <MetricCard 
                title="Average Duration" 
                value="2m 45s" 
                trend="-5s" 
                isNegativeTrend={true}
                icon={<Clock className="w-6 h-6 text-purple-400" />} 
                glowColor="rgba(168,85,247,0.5)"
              />
              <MetricCard 
                title="Success Rate" 
                value="94.2%" 
                trend="+2.1%" 
                icon={<CheckCircle className="w-6 h-6 text-emerald-400" />} 
                glowColor="rgba(52,211,153,0.5)"
              />
            </div>

            {/* CHARTS & ANALYTICS */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              
              {/* MAIN CHART */}
              <motion.div variants={itemVariants} className="lg:col-span-2 bg-slate-900/40 backdrop-blur-md rounded-2xl border border-slate-800/80 p-6 shadow-xl relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-b from-cyan-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                <h2 className="text-lg font-semibold mb-6 text-white flex items-center">
                  <Activity className="w-5 h-5 mr-2 text-cyan-500" />
                  Call Volume (Past 7 Days)
                </h2>
                <div className="h-72 w-full relative z-10">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData}>
                      <defs>
                        <linearGradient id="colorCalls" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#1e293b" />
                      <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{fill: '#64748b'}} dy={10} />
                      <YAxis axisLine={false} tickLine={false} tick={{fill: '#64748b'}} />
                      <Tooltip 
                        contentStyle={{ 
                          backgroundColor: 'rgba(15, 23, 42, 0.9)', 
                          backdropFilter: 'blur(8px)',
                          borderRadius: '12px', 
                          border: '1px solid rgba(30, 41, 59, 0.8)',
                          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.5)',
                          color: '#fff'
                        }}
                      />
                      <Area 
                        type="monotone" 
                        dataKey="calls" 
                        stroke="#06b6d4" 
                        strokeWidth={3}
                        fillOpacity={1}
                        fill="url(#colorCalls)"
                        activeDot={{r: 6, fill: '#06b6d4', stroke: '#fff', strokeWidth: 2, boxShadow: '0 0 10px #06b6d4'}} 
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>

              {/* AI INTENT BREAKDOWN */}
              <motion.div variants={itemVariants} className="bg-slate-900/40 backdrop-blur-md rounded-2xl border border-slate-800/80 p-6 shadow-xl">
                <h2 className="text-lg font-semibold mb-6 text-white">AI Intent Classification</h2>
                <div className="space-y-6">
                  <ProgressBar label="Technical Support" percentage={45} color="from-cyan-400 to-blue-500" />
                  <ProgressBar label="Sales Inquiry" percentage={30} color="from-purple-400 to-indigo-500" />
                  <ProgressBar label="Billing" percentage={15} color="from-emerald-400 to-teal-500" />
                  <ProgressBar label="Other / Unknown" percentage={10} color="from-slate-400 to-slate-500" />
                </div>
              </motion.div>
            </div>

            {/* RECENT CALLS TABLE */}
            <motion.div variants={itemVariants} className="bg-slate-900/40 backdrop-blur-md rounded-2xl border border-slate-800/80 overflow-hidden shadow-xl">
              <div className="px-6 py-5 border-b border-slate-800/80 flex items-center justify-between bg-slate-900/50">
                <h2 className="text-lg font-semibold text-white">Recent Calls</h2>
                <button className="text-sm text-cyan-400 hover:text-cyan-300 font-medium transition-colors">View All</button>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-900/20 border-b border-slate-800/60 text-xs uppercase tracking-wider text-slate-400 font-semibold">
                      <th className="px-6 py-4">Call ID</th>
                      <th className="px-6 py-4">Phone Number</th>
                      <th className="px-6 py-4">Duration</th>
                      <th className="px-6 py-4">Status</th>
                      <th className="px-6 py-4">AI Intent</th>
                      <th className="px-6 py-4">Date</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {recentCalls.map((call, i) => (
                      <motion.tr 
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.1 * i }}
                        key={i} 
                        className="hover:bg-slate-800/30 transition-colors cursor-pointer group"
                      >
                        <td className="px-6 py-4 text-sm font-medium text-cyan-400 group-hover:text-cyan-300 transition-colors">{call.id}</td>
                        <td className="px-6 py-4 text-sm text-slate-200">{call.phone}</td>
                        <td className="px-6 py-4 text-sm text-slate-400">{call.duration}</td>
                        <td className="px-6 py-4 text-sm">
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium border ${
                            call.status === 'Success' 
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                              : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
                          }`}>
                            {call.status === 'Success' ? <CheckCircle className="w-3 h-3 mr-1" /> : <AlertCircle className="w-3 h-3 mr-1" />}
                            {call.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-400">
                          <span className="bg-slate-800 px-2.5 py-1 rounded-md text-xs">{call.intent}</span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-500">{call.date}</td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>

          </motion.div>
        </main>
      </div>
    </div>
  );
}

// --- REUSABLE COMPONENTS ---

function NavItem({ icon, label, active, onClick }: { icon: React.ReactNode, label: string, active: boolean, onClick: () => void }) {
  return (
    <motion.button 
      whileHover={{ scale: 1.02, x: 4 }}
      whileTap={{ scale: 0.98 }}
      onClick={onClick}
      className={`w-full flex items-center px-4 py-3 rounded-xl transition-all duration-200 relative overflow-hidden ${
        active 
          ? 'bg-cyan-500/10 text-cyan-400 font-semibold border border-cyan-500/20' 
          : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 border border-transparent'
      }`}
    >
      {active && (
        <motion.div 
          layoutId="activeNavIndicator"
          className="absolute left-0 top-0 bottom-0 w-1 bg-cyan-500 shadow-[0_0_10px_#06b6d4]" 
        />
      )}
      <span className={`mr-3 ${active ? 'text-cyan-400 drop-shadow-[0_0_8px_rgba(6,182,212,0.8)]' : 'text-slate-500'}`}>
        {icon}
      </span>
      {label}
    </motion.button>
  );
}

function MetricCard({ title, value, trend, icon, glowColor, isNegativeTrend = false }: { title: string, value: string, trend: string, icon: React.ReactNode, glowColor: string, isNegativeTrend?: boolean }) {
  const isPositive = trend.startsWith('+') || (!isNegativeTrend && !trend.startsWith('-'));
  const trendColor = isPositive ? 'text-emerald-400' : 'text-rose-400';
  
  return (
    <motion.div 
      variants={itemVariants}
      whileHover={{ y: -5, boxShadow: `0 10px 30px -10px ${glowColor}` }}
      className="bg-slate-900/40 backdrop-blur-md rounded-2xl border border-slate-800/80 p-6 flex flex-col justify-between relative overflow-hidden group transition-all duration-300"
    >
      {/* Subtle background glow on hover */}
      <div 
        className="absolute -right-10 -top-10 w-32 h-32 rounded-full blur-[40px] opacity-0 group-hover:opacity-20 transition-opacity duration-500" 
        style={{ backgroundColor: glowColor.replace('0.5', '1') }}
      />
      
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className="p-3 bg-slate-800/50 rounded-xl border border-slate-700/50 shadow-inner">
          {icon}
        </div>
        <div className={`px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800/50 border border-slate-700/50 ${trendColor} flex items-center`}>
          {trend}
        </div>
      </div>
      
      <div className="relative z-10">
        <h3 className="text-3xl font-bold text-white tracking-tight mb-1">{value}</h3>
        <p className="text-sm font-medium text-slate-400">{title}</p>
      </div>
    </motion.div>
  );
}

function ProgressBar({ label, percentage, color }: { label: string, percentage: number, color: string }) {
  return (
    <div className="group">
      <div className="flex justify-between text-sm mb-2">
        <span className="text-slate-300 font-medium">{label}</span>
        <span className="text-slate-400 font-mono text-xs">{percentage}%</span>
      </div>
      <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden shadow-inner border border-slate-700/50">
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 1.5, ease: "easeOut" }}
          className={`bg-gradient-to-r ${color} h-full rounded-full relative`}
        >
          {/* Shimmer effect */}
          <div className="absolute top-0 right-0 bottom-0 w-20 bg-gradient-to-r from-transparent via-white/30 to-transparent -translate-x-full animate-[shimmer_2s_infinite]" />
        </motion.div>
      </div>
    </div>
  );
}
