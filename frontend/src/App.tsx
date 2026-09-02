import React, { useState } from 'react';
import axios from 'axios';
import {
  ShieldAlert,
  ShieldCheck,
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Lock,
  ArrowUpRight,
  Wifi,
  Battery,
  Signal,
  Info,
  Building2,
  User,
  Sparkles,
  Smartphone,
  BarChart3,
} from 'lucide-react';
import InvestigatorDashboard from './InvestigatorDashboard';

const API_BASE = 'http://localhost:8000';

type AppView = 'payer' | 'investigator';

type ScreenState =
  | 'home'
  | 'enter_payment'
  | 'verifying'
  | 'pin_entry'
  | 'explain_risk'
  | 'success';

interface SimulateResponse {
  decision: 'allow' | 'intercept';
  payer_event_id: number;
  risk_score: number;
  risk_bucket: string;
  evidence_summary: string;
  options?: string[];
}

const SAMPLE_HANDLES = [
  { upi: 'kennethscott91@upi', label: 'Clean Account', type: 'P2P', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
  { upi: 'jordanbates72@upi', label: 'Smurfing Pattern', type: 'Fraud Cluster', badge: 'bg-rose-500/20 text-rose-300 border-rose-500/30' },
  { upi: 'jordanchambers57@upi', label: 'Fan-In Pattern', type: 'Fraud Cluster', badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  { upi: 'rodriguezfigueroaandsanchez41@upi', label: 'Merchant Flash Sale', type: 'Legit Merchant', badge: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
];

export default function App() {
  const [appView, setAppView] = useState<AppView>('payer');
  const [screen, setScreen] = useState<ScreenState>('home');
  const [payeeUpi, setPayeeUpi] = useState('');
  const [amount, setAmount] = useState('');
  
  // API response & override states
  const [simResult, setSimResult] = useState<SimulateResponse | null>(null);
  const [isOverridden, setIsOverridden] = useState(false);
  
  // Risk explain screen states
  const [expandWhy, setExpandWhy] = useState(false);
  const [confirmInput, setConfirmInput] = useState('');
  const [showOverrideBox, setShowOverrideBox] = useState(false);
  const [showAlertModal, setShowAlertModal] = useState(false);
  
  // PIN screen state
  const [pin, setPin] = useState('');
  
  // Loading & error states
  const [verifyingText, setVerifyingText] = useState('Verifying payment...');

  // Reset payment workflow
  const resetPayment = () => {
    setPayeeUpi('');
    setAmount('');
    setSimResult(null);
    setIsOverridden(false);
    setExpandWhy(false);
    setConfirmInput('');
    setShowOverrideBox(false);
    setShowAlertModal(false);
    setPin('');
    setScreen('home');
  };

  // Start payment simulation
  const handleProceedToPay = async () => {
    setScreen('verifying');
    setVerifyingText('Verifying payment security...');

    const startTime = Date.now();

    try {
      const response = await axios.post<SimulateResponse>(`${API_BASE}/transactions/simulate`, {
        payer_account_id: 'demo_user@upi',
        payee_account_id: payeeUpi.trim(),
        amount: parseFloat(amount) || 0
      });

      // Ensure minimum 450ms delay for smooth loading animation
      const elapsedTime = Date.now() - startTime;
      const delay = Math.max(450 - elapsedTime, 0);

      setTimeout(() => {
        const data = response.data;
        setSimResult(data);

        if (data.decision === 'allow') {
          setIsOverridden(false);
          setScreen('pin_entry');
        } else {
          setScreen('explain_risk');
        }
      }, delay);

    } catch (err) {
      console.error('Simulation error:', err);
      // Fallback behavior if backend server is unreachable
      setTimeout(() => {
        setSimResult({
          decision: 'allow',
          payer_event_id: 999,
          risk_score: 0,
          risk_bucket: 'Low',
          evidence_summary: 'Payment check passed.'
        });
        setScreen('pin_entry');
      }, 450);
    }
  };

  // Resolve transaction API call
  const handleResolve = async (action: 'cancelled' | 'overrode_warning' | 'proceeded_normally') => {
    if (simResult?.payer_event_id) {
      try {
        await axios.post(`${API_BASE}/transactions/${simResult.payer_event_id}/resolve`, {
          action
        });
      } catch (err) {
        console.error('Resolve error:', err);
      }
    }
  };

  // Cancel Payment action
  const handleCancelPayment = async () => {
    await handleResolve('cancelled');
    resetPayment();
  };

  // Override Payment action
  const handleOverrideProceed = async () => {
    if (confirmInput.trim().toUpperCase() === 'CONFIRM') {
      await handleResolve('overrode_warning');
      setIsOverridden(true);
      setScreen('pin_entry');
    }
  };

  // PIN Submit action
  const handlePinSubmit = async () => {
    if (!isOverridden) {
      await handleResolve('proceeded_normally');
    }
    setScreen('success');
  };

  // Keypad click helper
  const handleKeypadPress = (val: string) => {
    if (val === 'back') {
      setPin(prev => prev.slice(0, -1));
    } else if (pin.length < 4) {
      setPin(prev => prev + val);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center font-sans text-slate-100 selection:bg-indigo-500/30">

      {/* ── Top-level Tab Navigation ── */}
      <div className="w-full max-w-5xl mx-auto px-4 pt-4 pb-2 flex items-center gap-1">
        <button
          onClick={() => setAppView('payer')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            appView === 'payer'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-950/40'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <Smartphone size={15} />
          Payer App
        </button>
        <button
          onClick={() => setAppView('investigator')}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
            appView === 'investigator'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-950/40'
              : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
          }`}
        >
          <BarChart3 size={15} />
          Investigator Dashboard
        </button>
      </div>

      {/* ── Investigator Dashboard View ── */}
      {appView === 'investigator' && (
        <div className="w-full max-w-5xl mx-auto px-4 pb-4 flex-1 flex flex-col min-h-0" style={{ height: 'calc(100vh - 72px)' }}>
          <div className="flex-1 bg-slate-900 rounded-2xl border border-slate-800 overflow-hidden flex flex-col shadow-2xl shadow-indigo-950/20">
            <InvestigatorDashboard />
          </div>
        </div>
      )}

      {/* ── Payer App View (Phone Frame) ── */}
      {appView === 'payer' && (
      <div className="flex-1 flex items-center justify-center p-4">
      <div className="w-full max-w-[390px] h-[780px] bg-slate-900 rounded-[48px] p-3 shadow-2xl border-4 border-slate-800 relative flex flex-col overflow-hidden shadow-indigo-950/40">
        
        {/* Phone Notch & Status Bar */}
        <div className="w-full h-8 flex items-center justify-between px-6 pt-2 select-none z-50">
          <span className="text-xs font-semibold text-slate-300">9:41</span>
          
          {/* Dynamic Island / Camera Notch */}
          <div className="w-24 h-4 bg-slate-950 rounded-full flex items-center justify-center gap-1.5 border border-slate-800/50">
            <div className="w-2 h-2 rounded-full bg-slate-800" />
            <div className="w-1.5 h-1.5 rounded-full bg-indigo-900/60" />
          </div>

          <div className="flex items-center gap-1.5 text-slate-400">
            <Signal size={12} />
            <Wifi size={12} />
            <Battery size={14} className="text-slate-300" />
          </div>
        </div>

        {/* Screen Content Container */}
        <div className="w-full h-full bg-slate-900 rounded-[38px] flex flex-col overflow-hidden relative border border-slate-800/80 shadow-inner">
          
          {/* SCREEN 1: HOME */}
          {screen === 'home' && (
            <div className="flex-1 p-5 flex flex-col justify-between overflow-y-auto">
              <div className="space-y-6">
                
                {/* App Header */}
                <div className="flex items-center justify-between pt-2">
                  <div className="flex items-center gap-2.5">
                    <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-emerald-400 flex items-center justify-center font-bold text-slate-950 text-sm shadow-md">
                      P
                    </div>
                    <div>
                      <h1 className="font-bold text-sm text-slate-100 leading-tight">PaySafe UPI</h1>
                      <p className="text-[11px] text-slate-400">Personal Account</p>
                    </div>
                  </div>
                  <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-1 rounded-full border border-slate-700 font-medium">
                    Demo Mode
                  </span>
                </div>

                {/* Balance Card */}
                <div className="bg-gradient-to-br from-indigo-600 via-indigo-700 to-slate-900 p-5 rounded-2xl shadow-xl border border-indigo-500/30 text-white relative overflow-hidden">
                  <div className="absolute -right-6 -bottom-6 w-32 h-32 bg-indigo-400/10 rounded-full blur-2xl pointer-events-none" />
                  <p className="text-xs text-indigo-200 font-medium">Available Balance</p>
                  <h2 className="text-3xl font-extrabold tracking-tight mt-1">₹24,850.00</h2>

                  {/* Primary Pay Button */}
                  <button
                    onClick={() => setScreen('enter_payment')}
                    className="w-full mt-5 bg-emerald-400 hover:bg-emerald-300 active:scale-95 text-slate-950 font-bold py-3 px-4 rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all cursor-pointer"
                  >
                    <ArrowUpRight size={18} className="stroke-[3]" />
                    <span>Pay Money</span>
                  </button>
                </div>

                {/* Recent Activity */}
                <div className="space-y-3">
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-1">
                    Recent Transactions
                  </h3>

                  <div className="bg-slate-950/60 rounded-2xl border border-slate-800/80 divide-y divide-slate-800/60">
                    <div className="p-3.5 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-300 text-xs font-semibold">
                          ☕
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-slate-200">Coffee Day</p>
                          <p className="text-[10px] text-slate-400">Today, 2:15 PM</p>
                        </div>
                      </div>
                      <span className="text-xs font-bold text-slate-300">- ₹240.00</span>
                    </div>

                    <div className="p-3.5 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs font-semibold">
                          ↓
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-slate-200">Priya Sharma</p>
                          <p className="text-[10px] text-slate-400">Yesterday</p>
                        </div>
                      </div>
                      <span className="text-xs font-bold text-emerald-400">+ ₹1,500.00</span>
                    </div>

                    <div className="p-3.5 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-slate-300 text-xs font-semibold">
                          🚇
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-slate-200">Metro Rail Recharge</p>
                          <p className="text-[10px] text-slate-400">28 Aug 2026</p>
                        </div>
                      </div>
                      <span className="text-xs font-bold text-slate-300">- ₹100.00</span>
                    </div>
                  </div>
                </div>

              </div>

              <div className="text-center pb-1">
                <p className="text-[11px] text-slate-500">Secured by TraceNet Real-time Risk Engine</p>
              </div>
            </div>
          )}

          {/* SCREEN 2: ENTER PAYMENT */}
          {screen === 'enter_payment' && (
            <div className="flex-1 p-5 flex flex-col justify-between overflow-y-auto">
              <div className="space-y-5">
                
                {/* Header */}
                <div className="flex items-center gap-3 pt-1">
                  <button
                    onClick={() => setScreen('home')}
                    className="p-1.5 rounded-full bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
                  >
                    <ArrowLeft size={18} />
                  </button>
                  <h2 className="font-bold text-base text-slate-100">Send Money via UPI</h2>
                </div>

                {/* Payee Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400">Recipient UPI ID</label>
                  <input
                    type="text"
                    value={payeeUpi}
                    onChange={e => setPayeeUpi(e.target.value)}
                    placeholder="e.g. name@upi or phone"
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3.5 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
                  />
                </div>

                {/* Sample Handles Row */}
                <div className="space-y-2">
                  <p className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
                    <Sparkles size={12} className="text-indigo-400" />
                    <span>Demo Accounts (Tap to Auto-fill):</span>
                  </p>
                  <div className="grid grid-cols-1 gap-2">
                    {SAMPLE_HANDLES.map((h, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => {
                          setPayeeUpi(h.upi);
                          if (!amount) setAmount('9600');
                        }}
                        className={`text-left p-2.5 rounded-xl border transition-all cursor-pointer flex items-center justify-between ${
                          payeeUpi === h.upi
                            ? 'bg-indigo-950/60 border-indigo-500/80 ring-1 ring-indigo-500/50'
                            : 'bg-slate-950/40 border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <div className="truncate">
                          <p className="text-xs font-semibold text-slate-200 truncate">{h.upi}</p>
                          <p className="text-[10px] text-slate-400">{h.label}</p>
                        </div>
                        <span className={`text-[10px] px-2 py-0.5 rounded-md border font-medium whitespace-nowrap ${h.badge}`}>
                          {h.type}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Amount Input */}
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-400">Amount (₹)</label>
                  <div className="relative">
                    <span className="absolute left-3.5 top-3 text-lg font-bold text-slate-400">₹</span>
                    <input
                      type="number"
                      value={amount}
                      onChange={e => setAmount(e.target.value)}
                      placeholder="0.00"
                      className="w-full bg-slate-950 border border-slate-800 rounded-xl pl-8 pr-3.5 py-2.5 text-xl font-bold text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500 transition-colors"
                    />
                  </div>
                  
                  {/* Quick Amount Chips */}
                  <div className="flex gap-2 pt-1">
                    {['100', '500', '1000', '9600'].map(amtVal => (
                      <button
                        key={amtVal}
                        type="button"
                        onClick={() => setAmount(amtVal)}
                        className="flex-1 py-1 bg-slate-800/80 hover:bg-slate-800 text-slate-300 text-[11px] font-semibold rounded-lg border border-slate-700/50 transition-colors"
                      >
                        +₹{amtVal}
                      </button>
                    ))}
                  </div>
                </div>

              </div>

              {/* Proceed Button */}
              <div className="pt-4 pb-2">
                <button
                  disabled={!payeeUpi.trim() || !amount || parseFloat(amount) <= 0}
                  onClick={handleProceedToPay}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:pointer-events-none text-white font-bold py-3.5 px-4 rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all cursor-pointer active:scale-95"
                >
                  <span>Proceed to Pay</span>
                </button>
              </div>
            </div>
          )}

          {/* SCREEN 3: RISK CHECK LOADING */}
          {screen === 'verifying' && (
            <div className="flex-1 p-6 flex flex-col items-center justify-center text-center space-y-6">
              <div className="relative">
                <div className="w-20 h-20 rounded-full bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center animate-pulse">
                  <ShieldCheck size={40} className="text-indigo-400" />
                </div>
                <Loader2 size={24} className="animate-spin text-indigo-400 absolute -top-1 -right-1" />
              </div>

              <div className="space-y-2 max-w-[260px]">
                <h3 className="font-bold text-base text-slate-100">{verifyingText}</h3>
                <p className="text-xs text-slate-400 leading-relaxed">
                  Evaluating graph topology, account age, and transaction velocity...
                </p>
              </div>
            </div>
          )}

          {/* SCREEN 4a: PIN ENTRY */}
          {screen === 'pin_entry' && (
            <div className="flex-1 p-5 flex flex-col justify-between">
              <div className="space-y-5 pt-2">
                
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setScreen('enter_payment')}
                    className="p-1.5 rounded-full bg-slate-800 text-slate-300 hover:text-white transition-colors cursor-pointer"
                  >
                    <ArrowLeft size={18} />
                  </button>
                  <h2 className="font-bold text-base text-slate-100">Enter 4-Digit UPI PIN</h2>
                </div>

                {/* Info Card */}
                <div className="bg-slate-950/70 p-4 rounded-2xl border border-slate-800 space-y-1 text-center">
                  <p className="text-xs text-slate-400">Paying to <span className="text-slate-200 font-semibold">{payeeUpi}</span></p>
                  <p className="text-2xl font-extrabold text-white">₹{parseFloat(amount).toLocaleString('en-IN')}</p>
                </div>

                {/* PIN Dots */}
                <div className="flex items-center justify-center gap-4 py-4">
                  {[0, 1, 2, 3].map(idx => (
                    <div
                      key={idx}
                      className={`w-4 h-4 rounded-full border-2 transition-all ${
                        pin.length > idx
                          ? 'bg-indigo-500 border-indigo-400 scale-110 shadow-lg shadow-indigo-500/50'
                          : 'border-slate-700 bg-slate-950'
                      }`}
                    />
                  ))}
                </div>

                {/* Numeric Keypad */}
                <div className="grid grid-cols-3 gap-3 max-w-[280px] mx-auto pt-2">
                  {['1','2','3','4','5','6','7','8','9','','0','back'].map((num, i) => (
                    <button
                      key={i}
                      type="button"
                      disabled={num === ''}
                      onClick={() => handleKeypadPress(num)}
                      className={`h-12 rounded-xl text-base font-bold transition-all ${
                        num === ''
                          ? 'opacity-0 pointer-events-none'
                          : 'bg-slate-800/80 hover:bg-slate-700 active:bg-slate-600 text-slate-100 active:scale-95 cursor-pointer'
                      }`}
                    >
                      {num === 'back' ? '⌫' : num}
                    </button>
                  ))}
                </div>

              </div>

              {/* Submit PIN Button */}
              <div className="pb-2">
                <button
                  disabled={pin.length < 4}
                  onClick={handlePinSubmit}
                  className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-slate-950 font-bold py-3.5 px-4 rounded-xl shadow-lg transition-all cursor-pointer active:scale-95"
                >
                  Confirm Payment
                </button>
              </div>
            </div>
          )}

          {/* SCREEN 4b: REAL-TIME EXPLAIN SCREEN (HIGH RISK PATH) */}
          {screen === 'explain_risk' && simResult && (
            <div className="flex-1 p-4 flex flex-col justify-between overflow-y-auto space-y-4">
              
              <div className="space-y-3 pt-1">
                
                {/* Warning Header Banner */}
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-4 flex items-start gap-3 relative overflow-hidden">
                  <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 shrink-0">
                    <ShieldAlert size={22} />
                  </div>
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-sm text-amber-300">Security Warning</h3>
                      <span className="text-[10px] font-extrabold bg-amber-500 text-slate-950 px-2 py-0.5 rounded-full uppercase">
                        {simResult.risk_bucket} RISK
                      </span>
                    </div>
                    <p className="text-[11px] text-amber-200/80 leading-snug">
                      TraceNet Risk Engine flagged suspicious structural patterns.
                    </p>
                  </div>
                </div>

                {/* Evidence Summary Prominent Box */}
                <div className="bg-slate-950 p-4 rounded-2xl border border-slate-800 space-y-2">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    Pattern Finding
                  </p>
                  <p className="text-xs text-slate-200 font-medium leading-relaxed bg-slate-900/80 p-3 rounded-xl border border-slate-800/80">
                    "{simResult.evidence_summary}"
                  </p>
                </div>

                {/* Expandable "Why am I seeing this?" Section */}
                <div className="bg-slate-950 rounded-2xl border border-slate-800 overflow-hidden">
                  <button
                    onClick={() => setExpandWhy(!expandWhy)}
                    className="w-full p-3.5 flex items-center justify-between text-xs font-semibold text-slate-300 hover:text-white transition-colors cursor-pointer"
                  >
                    <span className="flex items-center gap-2">
                      <Info size={15} className="text-indigo-400" />
                      Why am I seeing this warning?
                    </span>
                    {expandWhy ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>

                  {expandWhy && (
                    <div className="p-3.5 pt-0 border-t border-slate-800/60 space-y-3 text-xs">
                      
                      {/* Score Badge */}
                      <div className="flex items-center justify-between bg-slate-900 p-2.5 rounded-xl border border-slate-800">
                        <span className="text-slate-400 text-[11px]">Composite Risk Score:</span>
                        <span className="font-bold text-rose-400 bg-rose-500/10 px-2.5 py-0.5 rounded-md border border-rose-500/20">
                          {simResult.risk_score} / 100
                        </span>
                      </div>

                      {/* Plain Language Explanation */}
                      <p className="text-slate-300 text-[11px] leading-relaxed">
                        This recipient account is associated with transaction velocity anomalies typically observed in money laundering or mule operations.
                      </p>
                    </div>
                  )}
                </div>

                {/* Action 2: Review Modal (Placeholder) */}
                {showAlertModal && (
                  <div className="bg-indigo-950/80 border border-indigo-500/40 p-3 rounded-xl text-xs space-y-1 text-indigo-200 animate-fadeIn">
                    <p className="font-bold text-indigo-100">Beneficiary Security Insights:</p>
                    <p className="text-[11px]">Recipient account handle <span className="font-mono text-white">{payeeUpi}</span> exhibits abnormal incoming flow volume. Verify identity before transferring funds.</p>
                  </div>
                )}

              </div>

              {/* Action Buttons */}
              <div className="space-y-2 pb-1">
                
                {/* 1. Cancel Payment (Safe choice) */}
                <button
                  onClick={handleCancelPayment}
                  className="w-full bg-slate-800 hover:bg-slate-700 text-white font-bold py-3 px-4 rounded-xl shadow transition-all cursor-pointer text-xs flex items-center justify-center gap-2"
                >
                  <span>Cancel Payment</span>
                </button>

                {/* 2. Review Beneficiary */}
                <button
                  onClick={() => setShowAlertModal(!showAlertModal)}
                  className="w-full bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-200 font-semibold py-2.5 px-4 rounded-xl transition-all cursor-pointer text-xs flex items-center justify-center gap-2"
                >
                  <Info size={14} className="text-indigo-400" />
                  <span>{showAlertModal ? 'Hide Review' : 'Review Beneficiary'}</span>
                </button>

                {/* 3. Proceed Anyway (Override Option) */}
                {!showOverrideBox ? (
                  <button
                    onClick={() => setShowOverrideBox(true)}
                    className="w-full text-rose-400 hover:text-rose-300 font-semibold py-2 text-xs transition-colors cursor-pointer text-center"
                  >
                    Proceed anyway →
                  </button>
                ) : (
                  <div className="bg-slate-950 p-3 rounded-xl border border-rose-500/30 space-y-2 animate-fadeIn">
                    <p className="text-[11px] font-semibold text-rose-300">
                      Type <span className="font-mono font-bold text-white bg-slate-800 px-1 py-0.5 rounded">CONFIRM</span> to override warning:
                    </p>
                    <input
                      type="text"
                      value={confirmInput}
                      onChange={e => setConfirmInput(e.target.value)}
                      placeholder="Type CONFIRM"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs font-mono text-white placeholder:text-slate-600 focus:outline-none focus:border-rose-500"
                    />
                    <button
                      disabled={confirmInput.trim().toUpperCase() !== 'CONFIRM'}
                      onClick={handleOverrideProceed}
                      className="w-full bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white font-bold py-2 px-3 rounded-lg text-xs transition-all cursor-pointer"
                    >
                      I Understand the Risk — Continue
                    </button>
                  </div>
                )}

              </div>

            </div>
          )}

          {/* SCREEN 5a: SUCCESS */}
          {screen === 'success' && (
            <div className="flex-1 p-6 flex flex-col justify-between text-center">
              
              <div className="space-y-6 pt-8 my-auto">
                
                {/* Animated Green Checkmark */}
                <div className="w-20 h-20 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-400 flex items-center justify-center mx-auto shadow-xl shadow-emerald-950/50 animate-bounce">
                  <CheckCircle2 size={44} />
                </div>

                <div className="space-y-1">
                  <h2 className="font-extrabold text-xl text-white">Payment Successful</h2>
                  <p className="text-3xl font-extrabold text-emerald-400 pt-1">
                    ₹{parseFloat(amount).toLocaleString('en-IN')}
                  </p>
                  <p className="text-xs text-slate-400 pt-1">
                    Paid to <span className="font-semibold text-slate-200">{payeeUpi}</span>
                  </p>
                </div>

                {/* Overridden Subtle Note */}
                {isOverridden && (
                  <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px] font-medium mx-auto">
                    <AlertTriangle size={13} />
                    <span>Reviewed and confirmed by payer</span>
                  </div>
                )}

                <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-left text-[11px] space-y-1 text-slate-400 max-w-[260px] mx-auto">
                  <div className="flex justify-between">
                    <span>Ref ID:</span>
                    <span className="font-mono text-slate-300">TXN{Date.now().toString().slice(-8)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Status:</span>
                    <span className="text-emerald-400 font-semibold">Completed</span>
                  </div>
                </div>

              </div>

              {/* Done Button */}
              <div className="pb-2">
                <button
                  onClick={resetPayment}
                  className="w-full bg-slate-800 hover:bg-slate-700 text-white font-bold py-3.5 px-4 rounded-xl shadow-lg transition-all cursor-pointer active:scale-95"
                >
                  Done
                </button>
              </div>

            </div>
          )}

        </div>

      </div>
      </div>
      )}

    </div>
  );
}
