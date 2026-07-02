import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Mail, Lock, Eye, EyeOff, ArrowLeft } from 'lucide-react';
import { Button, Input, Card } from './ui-elements';
import logoImg from "../assets/veliora-logo.png";
import { ImageWithFallback } from './figma/ImageWithFallback';
import { UserRole } from '../types/erp';

interface AuthProps {
  onLogin: (email: string, password: string) => void;
  isLoading?: boolean;
  loginError?: string;
}

export const AuthView = ({ onLogin, isLoading: parentLoading, loginError }: AuthProps) => {
  const [mode, setMode] = useState<'login' | 'forgot'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const loading = parentLoading ?? false;

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    onLogin(email, password);
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-[420px]"
      >
        <div className="flex justify-center mb-8">
          <ImageWithFallback
            src={logoImg}
            alt="Company Logo"
            className="h-24 object-contain"
          />
        </div>

        <Card className="p-8 shadow-xl border-none">
          <AnimatePresence mode="wait">
            {mode === 'login' ? (
              <motion.div
                key="login"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="space-y-6"
              >
                <div className="text-center space-y-2">
                  <h1 className="text-2xl font-bold text-[#0F172A]">Employee Portal</h1>
                  <p className="text-[#64748B]">Welcome back! Please enter your details.</p>
                </div>

                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="relative">
                    <Input
                      label="Email or Employee ID"
                      type="text"
                      placeholder="E001 or name@company.com"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="pl-10"
                    />
                    <Mail className="absolute left-3 top-[38px] w-4 h-4 text-[#94A3B8]" />
                  </div>

                  <div className="relative">
                    <Input
                      label="Password"
                      type={showPassword ? 'text' : 'password'}
                      placeholder="••••••••"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="pl-10 pr-10"
                    />
                    <Lock className="absolute left-3 top-[38px] w-4 h-4 text-[#94A3B8]" />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-[38px] text-[#94A3B8] hover:text-[#64748B]"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  {loginError && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700 font-medium">
                      {loginError}
                    </div>
                  )}

                  <div className="flex items-center justify-end">
                    <button
                      type="button"
                      onClick={() => setMode('forgot')}
                      className="text-sm font-medium text-[#2563EB] hover:text-[#1D4ED8]"
                    >
                      Forgot Password?
                    </button>
                  </div>

                  <Button type="submit" className="w-full h-12 font-bold uppercase tracking-widest text-xs" isLoading={loading}>
                    Sign In
                  </Button>
                </form>

              </motion.div>
            ) : (
              <motion.div
                key="forgot"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-6"
              >
                <div className="text-center space-y-2">
                  <h1 className="text-2xl font-bold text-[#0F172A]">Forgot Password?</h1>
                  <p className="text-[#64748B]">
                    Password resets are handled by your system administrator.
                  </p>
                </div>

                <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 text-sm text-[#64748B] leading-relaxed">
                  Please contact your HR team or system administrator to have
                  your password reset. Once reset, you can change it anytime
                  from your profile after signing in.
                </div>

                <button
                  type="button"
                  onClick={() => setMode('login')}
                  className="flex items-center justify-center w-full text-sm font-medium text-[#64748B] hover:text-[#0F172A] pt-2"
                >
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back to Login
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>
      </motion.div>
    </div>
  );
};
