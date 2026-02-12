import { useEffect, useRef, useState } from 'react';
import { Terminal as XTerm } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import '@xterm/xterm/css/xterm.css';

interface TerminalProps {
  sessionId: string;
  token?: string;
  onCommand?: (command: string) => void;
  height?: string;
  executionOutput?: {
    status: 'idle' | 'running' | 'success' | 'error';
    stdout?: string;
    stderr?: string;
    error?: string;
    timestamp?: string;
  };
}

export const Terminal = ({ sessionId, token, onCommand, height = '300px', executionOutput }: TerminalProps) => {
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [commandHistory, setCommandHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const currentLineRef = useRef('');
  const cursorPositionRef = useRef(0);
  const lastExecutionTimestampRef = useRef<string | undefined>();

  useEffect(() => {
    if (!terminalRef.current) return;

    // Initialize XTerm
    const xterm = new XTerm({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Menlo, Monaco, "Courier New", monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#d4d4d4',
        cursor: '#ffffff',
        black: '#000000',
        red: '#cd3131',
        green: '#0dbc79',
        yellow: '#e5e510',
        blue: '#2472c8',
        magenta: '#bc3fbc',
        cyan: '#11a8cd',
        white: '#e5e5e5',
        brightBlack: '#666666',
        brightRed: '#f14c4c',
        brightGreen: '#23d18b',
        brightYellow: '#f5f543',
        brightBlue: '#3b8eea',
        brightMagenta: '#d670d6',
        brightCyan: '#29b8db',
        brightWhite: '#e5e5e5'
      },
      scrollback: 10000,
      convertEol: true
    });

    const fitAddon = new FitAddon();
    const webLinksAddon = new WebLinksAddon();

    xterm.loadAddon(fitAddon);
    xterm.loadAddon(webLinksAddon);

    xterm.open(terminalRef.current);
    
    // Delay fit to ensure DOM is ready
    setTimeout(() => {
      try {
        fitAddon.fit();
      } catch (error) {
        console.warn('Failed to fit terminal:', error);
      }
    }, 0);

    xtermRef.current = xterm;
    fitAddonRef.current = fitAddon;

    // Welcome message
    xterm.writeln('\x1b[1;36m╔════════════════════════════════════╗\x1b[0m');
    xterm.writeln('\x1b[1;36m║     \x1b[1;32mCoSim Terminal v1.0\x1b[1;36m         ║\x1b[0m');
    xterm.writeln('\x1b[1;36m╚════════════════════════════════════╝\x1b[0m');
    xterm.writeln(`Session: \x1b[1;33m${sessionId}\x1b[0m`);
    xterm.writeln('Connecting to remote shell...\n');

    // Connect to WebSocket terminal
    if (token) {
      const wsUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080')
        .replace('http://', 'ws://')
        .replace('https://', 'wss://');
      
      const ws = new WebSocket(`${wsUrl}/v1/sessions/${sessionId}/terminal?token=${token}`);
      
      ws.onopen = () => {
        setIsConnected(true);
        xterm.writeln('\x1b[1;32m✓\x1b[0m Connected to workspace');
        xterm.writeln('\x1b[90mType "help" for available commands\x1b[0m\n');
        xterm.write('\x1b[1;32m$\x1b[0m ');
        wsRef.current = ws;
      };

      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        
        if (data.type === 'output') {
          xterm.write(data.content);
        } else if (data.type === 'error') {
          xterm.writeln(`\x1b[1;31mError:\x1b[0m ${data.message}`);
          xterm.write('\x1b[1;32m$\x1b[0m ');
        } else if (data.type === 'prompt') {
          xterm.write('\x1b[1;32m$\x1b[0m ');
        } else if (data.type === 'exit') {
          xterm.writeln(`\n\x1b[90mProcess exited with code ${data.code}\x1b[0m`);
          xterm.write('\x1b[1;32m$\x1b[0m ');
        }
      };

      ws.onerror = () => {
        setIsConnected(false);
        xterm.writeln('\x1b[1;31m✗\x1b[0m Connection error');
        xterm.writeln('\x1b[90mRetrying in 3 seconds...\x1b[0m');
      };

      ws.onclose = () => {
        setIsConnected(false);
        xterm.writeln('\n\x1b[1;33m⚠\x1b[0m Connection closed');
      };
    } else {
      // Fallback mode without WebSocket
      setTimeout(() => {
        setIsConnected(true);
        xterm.writeln('\x1b[1;33m⚠\x1b[0m Running in local mode (no backend connection)');
        xterm.write('\x1b[1;32m$\x1b[0m ');
      }, 500);
    }

    // Handle user input
    xterm.onData(data => {
      const code = data.charCodeAt(0);
      
      // Handle Enter key
      if (code === 13) {
        xterm.write('\r\n');
        
        if (currentLineRef.current.trim()) {
          // Add to history
          setCommandHistory(prev => [...prev, currentLineRef.current]);
          setHistoryIndex(-1);

          // Send command via WebSocket or callback
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
              type: 'command',
              command: currentLineRef.current
            }));
          } else if (onCommand) {
            onCommand(currentLineRef.current);
          } else {
            // Local simulation
            simulateCommand(xterm, currentLineRef.current);
          }
        } else {
          xterm.write('\x1b[1;32m$\x1b[0m ');
        }
        
        currentLineRef.current = '';
        cursorPositionRef.current = 0;
      }
      // Handle Backspace
      else if (code === 127) {
        if (cursorPositionRef.current > 0) {
          currentLineRef.current = currentLineRef.current.slice(0, cursorPositionRef.current - 1) + 
                                    currentLineRef.current.slice(cursorPositionRef.current);
          cursorPositionRef.current--;
          xterm.write('\b \b');
        }
      }
      // Handle Ctrl+C
      else if (code === 3) {
        xterm.write('^C\r\n');
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
        }
        currentLineRef.current = '';
        cursorPositionRef.current = 0;
        xterm.write('\x1b[1;32m$\x1b[0m ');
      }
      // Handle Up Arrow (command history)
      else if (data === '\x1b[A') {
        if (commandHistory.length > 0) {
          const newIndex = historyIndex === -1 ? commandHistory.length - 1 : Math.max(0, historyIndex - 1);
          setHistoryIndex(newIndex);
          
          // Clear current line
          xterm.write('\r\x1b[K');
          xterm.write('\x1b[1;32m$\x1b[0m ');
          
          // Write historical command
          currentLineRef.current = commandHistory[newIndex];
          cursorPositionRef.current = currentLineRef.current.length;
          xterm.write(currentLineRef.current);
        }
      }
      // Handle Down Arrow
      else if (data === '\x1b[B') {
        if (historyIndex !== -1) {
          const newIndex = historyIndex === commandHistory.length - 1 ? -1 : historyIndex + 1;
          setHistoryIndex(newIndex);
          
          // Clear current line
          xterm.write('\r\x1b[K');
          xterm.write('\x1b[1;32m$\x1b[0m ');
          
          // Write command
          if (newIndex === -1) {
            currentLineRef.current = '';
            cursorPositionRef.current = 0;
          } else {
            currentLineRef.current = commandHistory[newIndex];
            cursorPositionRef.current = currentLineRef.current.length;
            xterm.write(currentLineRef.current);
          }
        }
      }
      // Handle Tab (autocomplete placeholder)
      else if (code === 9) {
        // TODO: Implement autocomplete
      }
      // Regular character
      else if (code >= 32) {
        currentLineRef.current = currentLineRef.current.slice(0, cursorPositionRef.current) + data + 
                                 currentLineRef.current.slice(cursorPositionRef.current);
        cursorPositionRef.current++;
        xterm.write(data);
      }
    });

    // Handle resize with debounce and safety checks
    let resizeTimeout: number | null = null;
    const handleResize = () => {
      if (resizeTimeout) {
        clearTimeout(resizeTimeout);
      }
      resizeTimeout = window.setTimeout(() => {
        try {
          if (fitAddonRef.current && xtermRef.current) {
            fitAddonRef.current.fit();
            if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify({
                type: 'resize',
                rows: xtermRef.current.rows,
                cols: xtermRef.current.cols
              }));
            }
          }
        } catch (error) {
          console.warn('Failed to resize terminal:', error);
        }
      }, 100);
    };

    window.addEventListener('resize', handleResize);

    // Simulate command execution for demo
    const simulateCommand = (xterm: XTerm, command: string) => {
      const parts = command.trim().split(' ');
      const cmd = parts[0];

      setTimeout(() => {
        switch (cmd) {
          case 'help':
            xterm.writeln('Available commands:');
            xterm.writeln('  \x1b[1;36mpython <file>\x1b[0m    - Run Python file');
            xterm.writeln('  \x1b[1;36mg++ <file>\x1b[0m       - Compile C++ file');
            xterm.writeln('  \x1b[1;36m./program\x1b[0m        - Run compiled binary');
            xterm.writeln('  \x1b[1;36mls\x1b[0m               - List files');
            xterm.writeln('  \x1b[1;36mcat <file>\x1b[0m       - Show file contents');
            xterm.writeln('  \x1b[1;36mclear\x1b[0m            - Clear terminal');
            break;
          case 'ls':
            xterm.writeln('src/');
            xterm.writeln('  main.py');
            xterm.writeln('  main.cpp');
            xterm.writeln('  utils.py');
            break;
          case 'clear':
            xterm.clear();
            break;
          case 'python':
            xterm.writeln('\x1b[1;32m✓\x1b[0m Running Python script...');
            xterm.writeln('Hello from CoSim');
            xterm.writeln('Running Python simulation...');
            break;
          case 'g++':
            xterm.writeln('\x1b[1;32m✓\x1b[0m Compiling C++ code...');
            xterm.writeln('Build successful: a.out');
            break;
          default:
            xterm.writeln(`\x1b[1;31mCommand not found:\x1b[0m ${cmd}`);
            xterm.writeln('Type "help" for available commands');
        }
        xterm.write('\x1b[1;32m$\x1b[0m ');
      }, 100);
    };

    return () => {
      window.removeEventListener('resize', handleResize);
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch (error) {
          console.warn('Failed to close WebSocket:', error);
        }
      }
      try {
        xterm.dispose();
      } catch (error) {
        console.warn('Failed to dispose terminal:', error);
      }
    };
  }, [sessionId, token, commandHistory, historyIndex]);

  // Display execution output when it changes
  useEffect(() => {
    if (!xtermRef.current || !executionOutput) return;
    
    // Prevent duplicate execution for the same timestamp
    if (executionOutput.timestamp && executionOutput.timestamp === lastExecutionTimestampRef.current) {
      console.log('📟 Skipping duplicate execution output (same timestamp)');
      return;
    }
    
    lastExecutionTimestampRef.current = executionOutput.timestamp;
    
    const xterm = xtermRef.current;
    
    // Debug log
    console.log('📟 Terminal received executionOutput:', {
      status: executionOutput.status,
      stdoutLength: executionOutput.stdout?.length,
      stderrLength: executionOutput.stderr?.length,
      stdoutPreview: executionOutput.stdout?.substring(0, 100),
      timestamp: executionOutput.timestamp
    });
    
    if (executionOutput.status === 'running') {
      console.log('📟 Status: running - writing execution message');
      xterm.writeln('\n\x1b[1;36m⚙️  Executing Python code...\x1b[0m');
    } else if (executionOutput.status === 'success') {
      console.log('📟 Status: success - writing output');
      xterm.writeln('\n\x1b[1;32m✓ Execution completed successfully\x1b[0m');
      
      if (executionOutput.stdout && executionOutput.stdout.trim()) {
        xterm.writeln('\x1b[1;36m━━━ Output ━━━\x1b[0m');
        // Split by lines and write each line (including empty lines for formatting)
        const lines = executionOutput.stdout.split('\n');
        console.log(`📟 Writing ${lines.length} lines to terminal:`, lines);
        lines.forEach((line, index) => {
          console.log(`  Line ${index}:`, line);
          // Always write the line, even if empty (preserves formatting)
          xterm.writeln(`\x1b[0;32m${line}\x1b[0m`);
        });
        xterm.writeln('\x1b[1;36m━━━━━━━━━━━━━━\x1b[0m\n');
      } else {
        xterm.writeln('\x1b[0;90m(No output produced)\x1b[0m\n');
      }
      
      if (executionOutput.stderr && executionOutput.stderr.trim()) {
        xterm.writeln('\x1b[1;33m━━━ Warnings ━━━\x1b[0m');
        executionOutput.stderr.split('\n').forEach(line => {
          xterm.writeln(`\x1b[0;33m${line}\x1b[0m`);
        });
        xterm.writeln('\x1b[1;33m━━━━━━━━━━━━━━\x1b[0m\n');
      }
      
      xterm.write('\x1b[1;32m$\x1b[0m ');
    } else if (executionOutput.status === 'error') {
      xterm.writeln('\n\x1b[1;31m✗ Execution failed\x1b[0m');
      
      if (executionOutput.error) {
        xterm.writeln(`\x1b[1;31mError:\x1b[0m ${executionOutput.error}`);
      }
      
      if (executionOutput.stderr) {
        executionOutput.stderr.split('\n').forEach(line => {
          xterm.writeln(`\x1b[0;31m${line}\x1b[0m`);
        });
      }
      
      xterm.writeln('');
      xterm.write('\x1b[1;32m$\x1b[0m ');
    }
  }, [executionOutput?.status, executionOutput?.timestamp, executionOutput?.stdout, executionOutput?.stderr]);

  return (
    <div
      ref={terminalRef}
      style={{
        height,
        width: '100%',
        background: '#1e1e1e',
        borderRadius: 0,
        overflow: 'hidden',
        position: 'relative'
      }}
    >
      {!isConnected && (
        <div style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          padding: '4px 8px',
          background: 'rgba(255, 193, 7, 0.9)',
          borderRadius: '4px',
          fontSize: '0.75rem',
          fontWeight: 600,
          color: '#000'
        }}>
          CONNECTING...
        </div>
      )}
      {isConnected && (
        <div style={{
          position: 'absolute',
          top: '8px',
          right: '8px',
          padding: '4px 8px',
          background: 'rgba(13, 188, 121, 0.9)',
          borderRadius: '4px',
          fontSize: '0.75rem',
          fontWeight: 600,
          color: '#fff'
        }}>
          ● CONNECTED
        </div>
      )}
    </div>
  );
};

export default Terminal;
