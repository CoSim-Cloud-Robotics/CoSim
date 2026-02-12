import { Pause, Play, RotateCcw, Settings, Maximize2, Camera, Download, Share2, Activity } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

interface SimulationViewerProps {
  sessionId: string;
  engine: 'mujoco' | 'pybullet';
  onControl?: (action: 'play' | 'pause' | 'reset' | 'step') => void;
  onRunCode?: () => Promise<void>;
  height?: string;
  executionOutput?: {
    status: 'idle' | 'running' | 'success' | 'error';
    stdout?: string;
    stderr?: string;
    error?: string;
    timestamp?: string;
  };
}

export const SimulationViewer = ({ sessionId, engine, onControl, onRunCode, height = '400px', executionOutput }: SimulationViewerProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const manualCloseRef = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [hasVideoStream, setHasVideoStream] = useState(false);
  const [fps, setFps] = useState(60);
  const fpsRef = useRef(fps);
  const [showSettings, setShowSettings] = useState(false);
  const [frameCount, setFrameCount] = useState(0);
  const [simulationTime, setSimulationTime] = useState(0);

  useEffect(() => {
    fpsRef.current = fps;
  }, [fps]);

  // Connect to WebSocket for simulation streaming
  const connectWebSocket = useCallback(() => {
    if (wsRef.current) {
      const readyState = wsRef.current.readyState;
      if (readyState === WebSocket.OPEN || readyState === WebSocket.CONNECTING) {
        console.log('ℹ️ Simulation stream WebSocket already active');
        return;
      }
    }

    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    const simulationApiUrl = import.meta.env.VITE_SIMULATION_API_URL || 'http://localhost:8005';
    const wsUrl = simulationApiUrl.replace('http://', 'ws://').replace('https://', 'wss://');
    const ws = new WebSocket(`${wsUrl}/simulations/${sessionId}/stream`);
    
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;
    manualCloseRef.current = false;
    
    ws.onopen = () => {
      console.log('✅ WebSocket connected to simulation stream');
      setIsConnected(true);
      setHasVideoStream(true);
      setIsPlaying(true);
      reconnectAttemptsRef.current = 0;
      
      // Send play command to start streaming
      ws.send('play');
    };
    
    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Received frame data
        const canvas = canvasRef.current;
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        
        try {
          // Convert ArrayBuffer to Blob
          const blob = new Blob([event.data], { type: 'image/jpeg' });
          const imageBitmap = await createImageBitmap(blob);
          
          // Draw frame to canvas
          canvas.width = imageBitmap.width;
          canvas.height = imageBitmap.height;
          ctx.drawImage(imageBitmap, 0, 0);
          
          // Update frame count
          setFrameCount(prev => prev + 1);
          setSimulationTime(prev => prev + (1 / fpsRef.current));
        } catch (error) {
          console.error('Failed to render frame:', error);
        }
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
      setIsPlaying(false);
      setHasVideoStream(false);
      wsRef.current = null;

      if (manualCloseRef.current) {
        manualCloseRef.current = false;
        reconnectAttemptsRef.current = 0;
        return;
      }

      const nextAttempt = reconnectAttemptsRef.current + 1;
      if (nextAttempt > 5) {
        console.warn('❌ Maximum WebSocket reconnect attempts reached');
        reconnectAttemptsRef.current = nextAttempt;
        return;
      }

      reconnectAttemptsRef.current = nextAttempt;
      const delay = Math.min(5000, nextAttempt * 1000);
      console.log(`🔄 Reconnecting to simulation stream in ${delay}ms (attempt ${nextAttempt})`);
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectWebSocket();
      }, delay);
    };
  }, [sessionId]);

  // Auto-start simulation when code execution completes successfully
  useEffect(() => {
    if (executionOutput?.status === 'success') {
      console.log('🎬 Code execution successful, starting WebSocket stream in 1s...');
      // Small delay to ensure simulation is ready
      const timer = setTimeout(() => {
        console.log('🔌 Connecting to WebSocket stream...');
        connectWebSocket();
      }, 1000);
      
      return () => clearTimeout(timer);
    }
  }, [executionOutput, connectWebSocket]);

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      manualCloseRef.current = true;
      if (reconnectTimeoutRef.current) {
        window.clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!wsRef.current) {
      return;
    }

    manualCloseRef.current = true;
    wsRef.current.close();
    wsRef.current = null;
    if (reconnectTimeoutRef.current) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    reconnectAttemptsRef.current = 0;
    setIsConnected(false);
    setIsPlaying(false);
    setHasVideoStream(false);
  }, [sessionId]);

  useEffect(() => {
    if (isConnected || hasVideoStream) {
      return;
    }

    let animationFrame: number | null = null;

    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) {
      return undefined;
    }

    canvas.width = 800;
    canvas.height = 600;

    const render = (time: number) => {
      if (wsRef.current) {
        return;
      }

      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      ctx.strokeStyle = 'rgba(102, 126, 234, 0.2)';
      ctx.lineWidth = 1;

      const gridSize = 40;
      for (let x = 0; x <= canvas.width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }
      for (let y = 0; y <= canvas.height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      const elapsed = time / 1000;
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;
      const size = 80;
      const rotation = elapsed * 0.5;

      ctx.save();
      ctx.translate(centerX, centerY);
      ctx.rotate(rotation);

      ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
      ctx.fillRect(-size * 0.6, size + 10, size * 1.2, 20);

      const gradient = ctx.createLinearGradient(-size / 2, -size / 2, size / 2, size / 2);
      gradient.addColorStop(0, '#667eea');
      gradient.addColorStop(1, '#764ba2');

      ctx.fillStyle = gradient;
      ctx.fillRect(-size / 2, -size / 2, size, size);

      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 2;
      ctx.strokeRect(-size / 2, -size / 2, size, size);

      ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(-size / 2, 0);
      ctx.lineTo(size / 2, 0);
      ctx.moveTo(0, -size / 2);
      ctx.lineTo(0, size / 2);
      ctx.stroke();

      ctx.restore();

      ctx.fillStyle = '#e2e8f0';
      ctx.font = '12px monospace';
      ctx.fillText(`${engine.toUpperCase()} Simulation`, 10, 20);
      ctx.fillText('Awaiting stream…', 10, 40);
    };

    const loop = (time: number) => {
      render(time);
      animationFrame = requestAnimationFrame(loop);
    };

    animationFrame = requestAnimationFrame(loop);

    return () => {
      if (animationFrame !== null) {
        cancelAnimationFrame(animationFrame);
      }
    };
  }, [sessionId, engine, isConnected, hasVideoStream]);

  const handleControl = async (action: 'play' | 'pause' | 'reset' | 'step') => {
    if (action === 'play') {
      // Trigger code execution if callback is provided
      if (onRunCode) {
        try {
          await onRunCode();
          console.log('\u2705 Code execution completed, starting simulation');
        } catch (error) {
          console.error('\u274c Code execution failed:', error);
          return; // Don't start playing if code failed
        }
      }
      
      // Send play command via WebSocket if connected
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send('play');
      } else {
        // If not connected, establish WebSocket connection
        connectWebSocket();
      }
    }
    
    if (action === 'pause') {
      setIsPlaying(false);
      
      // Send pause command via WebSocket
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send('pause');
      }
    }
    
    if (action === 'reset') {
      setIsPlaying(false);
      setFrameCount(0);
      setSimulationTime(0);
      
      // Send reset command via WebSocket
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send('reset');
      }
      
      // Clear canvas
      if (canvasRef.current) {
        const ctx = canvasRef.current.getContext('2d');
        if (ctx) {
          ctx.fillStyle = '#0a0a0a';
          ctx.fillRect(0, 0, canvasRef.current.width, canvasRef.current.height);
        }
      }
    }
    
    if (onControl) {
      onControl(action);
    }
  };

  return (
    <div style={{ height, display: 'flex', flexDirection: 'column', backgroundColor: '#0a0a0a', position: 'relative' }}>
      {/* Enhanced Toolbar */}
      <div style={{
        padding: '0.75rem 1.25rem',
        background: 'linear-gradient(135deg, #1a1a1a 0%, #2d2d30 100%)',
        borderBottom: '1px solid rgba(102, 126, 234, 0.2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        backdropFilter: 'blur(10px)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.4rem 0.75rem',
            background: 'rgba(102, 126, 234, 0.1)',
            borderRadius: '8px',
            border: '1px solid rgba(102, 126, 234, 0.2)'
          }}>
            <div style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              backgroundColor: isConnected ? '#0dbc79' : '#ce9178',
              boxShadow: isConnected ? '0 0 8px #0dbc79' : '0 0 8px #ce9178',
              animation: isConnected ? 'pulse 2s ease-in-out infinite' : 'none'
            }} />
            <span style={{ fontSize: '0.85rem', color: '#e2e8f0', fontWeight: 600 }}>
              {engine === 'mujoco' ? 'MuJoCo' : 'PyBullet'}
            </span>
          </div>
          
          {isConnected && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              fontSize: '0.75rem',
              color: '#94a3b8'
            }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <Activity size={12} color="#0dbc79" />
                {fps} FPS
              </span>
              <span style={{ color: '#64748b' }}>•</span>
              <span>Frame {frameCount}</span>
              <span style={{ color: '#64748b' }}>•</span>
              <span>{simulationTime.toFixed(2)}s</span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <ActionButton
            onClick={() => handleControl(isPlaying ? 'pause' : 'play')}
            disabled={!isConnected}
            icon={isPlaying ? <Pause size={14} /> : <Play size={14} />}
            label={isPlaying ? 'Pause' : 'Play'}
            variant={isPlaying ? 'warning' : 'primary'}
          />
          
          <ActionButton
            onClick={() => handleControl('reset')}
            disabled={!isConnected}
            icon={<RotateCcw size={14} />}
            label="Reset"
            variant="secondary"
          />

          <div style={{ width: '1px', height: '24px', background: '#3e3e42', margin: '0 0.25rem' }} />

          <ActionButton
            onClick={() => {}}
            disabled={!isConnected}
            icon={<Camera size={14} />}
            variant="secondary"
            tooltip="Screenshot"
          />

          <ActionButton
            onClick={() => {}}
            disabled={!isConnected}
            icon={<Download size={14} />}
            variant="secondary"
            tooltip="Export"
          />

          <ActionButton
            onClick={() => {}}
            disabled={!isConnected}
            icon={<Share2 size={14} />}
            variant="secondary"
            tooltip="Share"
          />

          <div style={{ width: '1px', height: '24px', background: '#3e3e42', margin: '0 0.25rem' }} />

          <ActionButton
            onClick={() => setShowSettings(!showSettings)}
            disabled={!isConnected}
            icon={<Settings size={14} />}
            variant="secondary"
            active={showSettings}
          />

          <ActionButton
            onClick={() => {}}
            disabled={!isConnected}
            icon={<Maximize2 size={14} />}
            variant="secondary"
            tooltip="Fullscreen"
          />
        </div>
      </div>

      {/* Enhanced Settings Panel */}
      {showSettings && (
        <div style={{
          padding: '1.25rem',
          background: 'linear-gradient(135deg, #252526 0%, #1e1e1e 100%)',
          borderBottom: '1px solid rgba(102, 126, 234, 0.2)',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '1rem'
        }}>
          <SettingControl
            label="Frame Rate"
            value={fps}
            options={[30, 60, 120]}
            onChange={setFps}
          />
          <SettingControl
            label="Quality"
            value="High"
            options={['Low', 'Medium', 'High', 'Ultra']}
            onChange={() => {}}
          />
          <SettingControl
            label="Camera Mode"
            value="Follow"
            options={['Fixed', 'Follow', 'Free']}
            onChange={() => {}}
          />
        </div>
      )}

      {/* Enhanced Video/Canvas Area */}
      <div style={{
        flex: 1,
        position: 'relative',
        background: 'radial-gradient(circle at 50% 50%, #1a1a1a 0%, #0a0a0a 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        overflow: 'hidden'
      }}>
        {/* Grid Background Pattern */}
        <div style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(rgba(102, 126, 234, 0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(102, 126, 234, 0.05) 1px, transparent 1px)
          `,
          backgroundSize: '50px 50px',
          opacity: 0.3
        }} />

        {!isConnected ? (
          <div style={{
            textAlign: 'center',
            zIndex: 1,
            padding: '2rem',
            background: 'rgba(26, 26, 26, 0.8)',
            backdropFilter: 'blur(10px)',
            borderRadius: '16px',
            border: '1px solid rgba(102, 126, 234, 0.2)'
          }}>
            <div style={{
              width: '60px',
              height: '60px',
              margin: '0 auto 1rem',
              borderRadius: '50%',
              border: '3px solid rgba(102, 126, 234, 0.3)',
              borderTopColor: '#667eea',
              animation: 'spin 1s linear infinite'
            }} />
            <div style={{ fontSize: '1rem', marginBottom: '0.5rem', color: '#e2e8f0', fontWeight: 600 }}>
              Connecting to simulation...
            </div>
            <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
              Initializing WebRTC stream
            </div>
          </div>
        ) : (
          <>
            {/* WebRTC Video Stream */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                zIndex: 1,
                display: hasVideoStream ? 'none' : 'block' // Hide if using canvas
              }}
            />
            
            {/* Canvas for rendering (fallback or overlay) */}
            <canvas
              ref={canvasRef}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 2,
                display: hasVideoStream ? 'block' : 'none' // Show when active
              }}
            />

            {/* Placeholder Content - Only show if no video stream AND not playing */}
            {!hasVideoStream && !isPlaying && (
              <div style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 3
              }}>
                <div style={{
                  textAlign: 'center',
                  padding: '2rem',
                  background: 'rgba(26, 26, 26, 0.95)',
                  backdropFilter: 'blur(10px)',
                  borderRadius: '16px',
                  border: '1px solid rgba(102, 126, 234, 0.2)',
                  maxWidth: '400px'
                }}>
                  <div style={{ fontSize: '3.5rem', marginBottom: '1rem' }}>🤖</div>
                  <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '1.25rem', fontWeight: 700, color: '#e2e8f0' }}>
                    Simulation Ready
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.9rem', color: '#94a3b8', lineHeight: 1.6 }}>
                    {engine === 'mujoco' ? 'MuJoCo' : 'PyBullet'} engine initialized.
                    <br />
                    Press <strong style={{ color: '#667eea' }}>Play</strong> to start the simulation.
                  </p>
                </div>
              </div>
            )}

            {/* Status Overlay */}
            <div style={{
              position: 'absolute',
              bottom: '1.5rem',
              right: '1.5rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
              zIndex: 3
            }}>
              <div style={{
                background: 'rgba(26, 26, 26, 0.9)',
                backdropFilter: 'blur(10px)',
                padding: '0.75rem 1rem',
                borderRadius: '10px',
                fontSize: '0.8rem',
                color: '#e2e8f0',
                border: '1px solid rgba(102, 126, 234, 0.2)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem'
              }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  paddingRight: '0.75rem',
                  borderRight: '1px solid rgba(226, 232, 240, 0.2)'
                }}>
                  <div style={{
                    width: '8px',
                    height: '8px',
                    borderRadius: '50%',
                    backgroundColor: isPlaying ? '#0dbc79' : '#f59e0b',
                    boxShadow: isPlaying ? '0 0 8px #0dbc79' : '0 0 8px #f59e0b'
                  }} />
                  <span style={{ fontWeight: 600 }}>{isPlaying ? 'Running' : 'Paused'}</span>
                </div>
                <span>Frame {frameCount}</span>
              </div>
            </div>
          </>
        )}
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

// Helper Components
interface ActionButtonProps {
  onClick: () => void;
  disabled?: boolean;
  icon: React.ReactNode;
  label?: string;
  variant?: 'primary' | 'secondary' | 'warning';
  active?: boolean;
  tooltip?: string;
}

const ActionButton = ({ onClick, disabled, icon, label, variant = 'secondary', active, tooltip }: ActionButtonProps) => {
  const getVariantStyles = () => {
    if (disabled) {
      return {
        background: 'rgba(100, 116, 139, 0.1)',
        border: '1px solid rgba(100, 116, 139, 0.2)',
        color: '#475569',
        cursor: 'not-allowed'
      };
    }

    switch (variant) {
      case 'primary':
        return {
          background: 'linear-gradient(135deg, #0dbc79 0%, #23d18b 100%)',
          border: '1px solid rgba(13, 188, 121, 0.3)',
          color: '#fff',
          cursor: 'pointer'
        };
      case 'warning':
        return {
          background: 'linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)',
          border: '1px solid rgba(245, 158, 11, 0.3)',
          color: '#000',
          cursor: 'pointer'
        };
      default:
        return {
          background: active ? 'rgba(102, 126, 234, 0.2)' : 'rgba(148, 163, 184, 0.1)',
          border: `1px solid ${active ? 'rgba(102, 126, 234, 0.4)' : 'rgba(148, 163, 184, 0.2)'}`,
          color: active ? '#e2e8f0' : '#94a3b8',
          cursor: 'pointer'
        };
    }
  };

  const styles = getVariantStyles();

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={tooltip}
      style={{
        ...styles,
        borderRadius: '8px',
        padding: label ? '0.5rem 0.875rem' : '0.5rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.4rem',
        fontSize: '0.85rem',
        fontWeight: 600,
        transition: 'all 0.2s',
        outline: 'none'
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          e.currentTarget.style.transform = 'translateY(-1px)';
          e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.2)';
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {icon}
      {label && <span>{label}</span>}
    </button>
  );
};

interface SettingControlProps {
  label: string;
  value: string | number;
  options: (string | number)[];
  onChange: (value: any) => void;
}

const SettingControl = ({ label, value, options, onChange }: SettingControlProps) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
    <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      {label}
    </label>
    <select
      value={value}
      onChange={(e) => {
        const val = typeof options[0] === 'number' ? Number(e.target.value) : e.target.value;
        onChange(val);
      }}
      style={{
        padding: '0.5rem 0.75rem',
        background: 'rgba(26, 26, 26, 0.8)',
        color: '#e2e8f0',
        border: '1px solid rgba(102, 126, 234, 0.2)',
        borderRadius: '8px',
        fontSize: '0.9rem',
        fontWeight: 500,
        cursor: 'pointer',
        outline: 'none',
        transition: 'all 0.2s'
      }}
      onFocus={(e) => {
        e.currentTarget.style.borderColor = '#667eea';
        e.currentTarget.style.boxShadow = '0 0 0 3px rgba(102, 126, 234, 0.1)';
      }}
      onBlur={(e) => {
        e.currentTarget.style.borderColor = 'rgba(102, 126, 234, 0.2)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    >
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  </div>
);

export default SimulationViewer;
