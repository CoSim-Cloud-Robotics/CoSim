import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Editor, { OnChange, OnMount } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import * as Y from 'yjs';
import { WebsocketProvider } from 'y-websocket';
import { MonacoBinding } from 'y-monaco';

import FileTree, { FileNode } from './FileTree';
import Terminal from './Terminal';
import { buildCpp, executeBinary, executePython } from '../api/execution';
import { deleteWorkspacePath, listWorkspaceFiles, renameWorkspacePath, upsertWorkspaceFile } from '../api/workspaceFiles';
import { getGitStatus, gitAdd, gitCommit } from '../api/git';
import { startDebugSession, stopDebugSession } from '../api/debug';
import { useAuth } from '../hooks/useAuth';
import { Upload, FolderUp } from 'lucide-react';

const AUTO_SAVE_INTERVAL_MS = 3000;
const PLACEHOLDER_WORKSPACE_PREFIX = 'placeholder';

type SupportedLanguage = 'python' | 'cpp' | 'text';

const darkPlusTheme: monaco.editor.IStandaloneThemeData = {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: '', foreground: 'd4d4d4', background: '1e1e1e' },
    { token: 'comment', foreground: '6a9955' },
    { token: 'string', foreground: 'ce9178' },
    { token: 'number', foreground: 'b5cea8' },
    { token: 'type', foreground: '4ec9b0' },
    { token: 'keyword', foreground: 'c586c0' },
    { token: 'keyword.flow', foreground: 'c586c0' },
    { token: 'variable', foreground: '9cdcfe' },
    { token: 'identifier', foreground: '9cdcfe' },
    { token: 'delimiter', foreground: 'd4d4d4' },
    { token: 'predefined', foreground: 'c586c0' }
  ],
  colors: {
    'editor.background': '#1e1e1e',
    'editor.foreground': '#d4d4d4',
    'editorCursor.foreground': '#aeafad',
    'editor.lineHighlightBackground': '#2a2d2e',
    'editor.selectionBackground': '#264f78',
    'editor.inactiveSelectionBackground': '#3a3d41',
    'editor.selectionHighlightBackground': '#add6ff26',
    'editorLineNumber.foreground': '#858585',
    'editorLineNumber.activeForeground': '#c6c6c6',
    'editorGutter.background': '#1e1e1e',
    'editorGutter.modifiedBackground': '#d7ba7d',
    'editorGutter.addedBackground': '#81b88b',
    'editorGutter.deletedBackground': '#c74e39',
    'editorError.foreground': '#f14c4c',
    'editorWarning.foreground': '#cca700',
    'editorInfo.foreground': '#3794ff',
    'editorHint.foreground': '#4fc1ff',
    'editorBracketMatch.border': '#515a6b',
    'editorIndentGuide.background': '#404040',
    'editorIndentGuide.activeBackground': '#707070',
    'editorWhitespace.foreground': '#3b3a32',
    'editorRuler.foreground': '#5a5a5a',
    'minimap.selectionHighlight': '#264f78',
    'diffEditor.insertedTextBackground': '#81b88b33',
    'diffEditor.removedTextBackground': '#c74e3933',
    'diffEditor.insertedLineBackground': '#81b88b1a',
    'diffEditor.removedLineBackground': '#c74e391a',
    'diffEditorGutter.insertedLineBackground': '#81b88b55',
    'diffEditorGutter.removedLineBackground': '#c74e3955',
    'peekView.border': '#3794ff',
    'peekViewEditor.background': '#1e1e1e',
    'peekViewEditor.matchHighlightBackground': '#2f71c6',
    'peekViewResult.background': '#252526',
    'peekViewResult.matchHighlightBackground': '#2f71c6',
    'peekViewTitle.background': '#1e1e1e',
    'peekViewTitleDescription.foreground': '#9ca3af',
    'editor.findMatchBackground': '#515c6a',
    'editor.findMatchHighlightBackground': '#45546a',
    'editor.findRangeHighlightBackground': '#3a3d4166',
    'editor.hoverHighlightBackground': '#264f7826',
    'editor.wordHighlightStrongBackground': '#264f7833',
    'editor.wordHighlightBackground': '#264f781a',
    'editorInlayHint.background': '#2a2d2e',
    'editorInlayHint.foreground': '#9ca3af',
    'editorInlayHint.typeForeground': '#a6accd',
    'editorInlayHint.typeBackground': '#2a2d2e',
    'editorInlayHint.parameterForeground': '#a6accd',
    'editorInlayHint.parameterBackground': '#2a2d2e',
    'problemsErrorIcon.foreground': '#f14c4c',
    'problemsWarningIcon.foreground': '#cca700',
    'problemsInfoIcon.foreground': '#3794ff'
  }
};

interface WorkspaceFileDescriptor {
  path: string;
  content: string;
  language?: SupportedLanguage | null;
}

const DEFAULT_FILE_TEMPLATES: WorkspaceFileDescriptor[] = [
  {
    path: '/src/main.py',
    content: '# Python session starter\nimport numpy as np\n\n\ndef main():\n    print("Hello from CoSim")\n    print("Running Python simulation...")\n\n\nif __name__ == "__main__":\n    main()\n',
    language: 'python'
  },
  {
    path: '/src/cartpole_sim.py',
    content: `# CoSim MuJoCo Cartpole Control Script
# This demonstrates how to control a MuJoCo simulation

import numpy as np

class CartpoleController:
    """Simple PD controller for cartpole balancing."""
    
    def __init__(self, kp_pole=50.0, kd_pole=10.0):
        self.kp_pole = kp_pole
        self.kd_pole = kd_pole
    
    def compute_action(self, state):
        """Compute control action based on current state."""
        pole_angle = state['qpos'][1]
        pole_vel = state['qvel'][1]
        
        # PD control to balance pole
        action = -self.kp_pole * pole_angle - self.kd_pole * pole_vel
        return np.clip(action, -10.0, 10.0)

def main():
    print("🚀 Starting Cartpole Simulation...")
    
    controller = CartpoleController()
    
    # Get simulation (injected by CoSim)
    sim = get_simulation()
    
    # Reset simulation
    state = sim.reset()
    print(f"✓ Initial angle: {state['qpos'][1]:.3f} rad")
    
    # Run simulation loop continuously
    i = 0
    while True:  # Continuous simulation
        state = sim.get_state()
        action = controller.compute_action(state)
        state = sim.step(np.array([action]))
        
        if i % 50 == 0:
            print(f"Step {i:3d} | Pole: {state['qpos'][1]:+.3f}rad")
        
        # Check if pole fell - reset if needed
        if abs(state['qpos'][1]) > 0.5:
            print(f"⚠️ Pole fell at step {i}, resetting...")
            state = sim.reset()
        
        i += 1
        
        # Small delay to prevent overwhelming (60 FPS)
        if i % 1000 == 0:
            print(f"✓ Still running smoothly at step {i}!")
    
    print(f"🏁 Simulation ended")  # This won't be reached


if __name__ == "__main__":
    main()
`,
    language: 'python'
  },
  {
    path: '/models/cartpole.xml',
    content: `<mujoco model="cartpole">
  <compiler angle="radian" inertiafromgeom="true"/>
  
  <default>
    <joint armature="0" damping="0.1" limited="true"/>
    <geom conaffinity="0" condim="3" contype="1" friction="1 0.1 0.1" 
          rgba="0.8 0.6 0.4 1" density="1000"/>
  </default>

  <option gravity="0 0 -9.81" integrator="RK4" timestep="0.01"/>

  <worldbody>
    <light cutoff="100" diffuse="1 1 1" dir="-0 0 -1.3" directional="true" 
          exponent="1" pos="0 0 1.3" specular=".1 .1 .1"/>
    
    <geom name="floor" pos="0 0 -0.6" size="2.5 2.5 0.05" type="plane" 
          rgba="0.9 0.9 0.9 1"/>
    
    <body name="cart" pos="0 0 0">
      <joint name="slider" type="slide" pos="0 0 0" axis="1 0 0" 
             range="-1 1" damping="0.1"/>
      <geom name="cart" type="box" pos="0 0 0" size="0.2 0.15 0.1" 
            rgba="0.2 0.8 0.2 1" mass="1"/>
      
      <body name="pole" pos="0 0 0">
        <joint name="hinge" type="hinge" pos="0 0 0" axis="0 1 0" 
               range="-3.14 3.14" damping="0.01"/>
        <geom name="cpole" type="capsule" fromto="0 0 0 0 0 0.6" 
              size="0.045" rgba="0.8 0.2 0.2 1" mass="0.1"/>
        <geom name="ball" type="sphere" pos="0 0 0.6" size="0.08" 
              rgba="0.8 0.2 0.2 1" mass="0.05"/>
      </body>
    </body>
  </worldbody>

  <actuator>
    <motor joint="slider" gear="100" ctrllimited="true" ctrlrange="-10 10"/>
  </actuator>
</mujoco>`,
    language: 'text'
  },
  {
    path: '/src/utils.py',
    content: '# Utility functions\n\ndef helper():\n    """Helper function"""\n    pass\n',
    language: 'python'
  },
  {
    path: '/src/main.cpp',
    content: '#include <iostream>\n#include <vector>\n\nint main() {\n    std::cout << "Hello from CoSim" << std::endl;\n    std::cout << "C++ simulation starting..." << std::endl;\n    return 0;\n}\n',
    language: 'cpp'
  },
  {
    path: '/config/sim-control.json',
    content: '{\n  "engine": "mujoco",\n  "seed": 42,\n  "reset": false,\n  "stepping_mode": "manual"\n}\n',
    language: 'text'
  }
];

const PANEL_TABS = ['Terminal', 'Output', 'Debug Console', 'Problems'] as const;
type PanelTab = typeof PANEL_TABS[number];

const PRESENCE_COLORS = ['#f59e0b', '#34d399', '#60a5fa', '#f472b6', '#22d3ee', '#c084fc', '#f87171'];

const inferLanguage = (path: string, explicit?: string | null): SupportedLanguage => {
  if (explicit === 'python' || explicit === 'cpp' || explicit === 'text') {
    return explicit;
  }
  if (path.endsWith('.py')) return 'python';
  if (path.endsWith('.cpp') || path.endsWith('.cc') || path.endsWith('.hpp')) return 'cpp';
  return 'text';
};

const buildFileTree = (files: WorkspaceFileDescriptor[], extraDirectories: string[] = []): FileNode[] => {
  const root: FileNode = {
    id: 'root',
    name: 'workspace',
    type: 'directory',
    path: '/',
    children: []
  };

  const ensureChildDirectory = (parent: FileNode, name: string, path: string) => {
    if (!parent.children) parent.children = [];
    let directory = parent.children.find(child => child.type === 'directory' && child.name === name);
    if (!directory) {
      directory = {
        id: `dir-${path}`,
        name,
        type: 'directory',
        path,
        children: []
      };
      parent.children.push(directory);
    }
    return directory;
  };

  const addDirectoryPath = (dirPath: string) => {
    const segments = dirPath.split('/').filter(Boolean);
    let current = root;
    let currentPath = '';
    segments.forEach(segment => {
      currentPath = `${currentPath}/${segment}`;
      current = ensureChildDirectory(current, segment, currentPath);
    });
  };

  extraDirectories.forEach(addDirectoryPath);

  for (const file of files) {
    const segments = file.path.split('/').filter(Boolean);
    if (segments.length === 0) {
      continue;
    }

    let current = root;
    let currentPath = '';

    segments.forEach((segment, index) => {
      currentPath = `${currentPath}/${segment}`;
      const isFile = index === segments.length - 1;

      if (isFile) {
        if (!current.children) current.children = [];
        const existingFile = current.children.find(child => child.type === 'file' && child.path === currentPath);
        if (!existingFile) {
          current.children.push({
            id: currentPath,
            name: segment,
            type: 'file',
            path: currentPath,
            language: inferLanguage(currentPath, file.language)
          });
        }
      } else {
        current = ensureChildDirectory(current, segment, currentPath);
      }
    });
  }

  const sortTree = (node: FileNode) => {
    if (!node.children) return;
    node.children.sort((a, b) => {
      if (a.type === b.type) return a.name.localeCompare(b.name);
      return a.type === 'directory' ? -1 : 1;
    });
    node.children.forEach(sortTree);
  };

  sortTree(root);
  return [root];
};

interface Props {
  sessionId?: string;
  workspaceId?: string;
  enableCollaboration?: boolean;
  onSave?: (payload: { path: string; content: string }) => void;
  onRunSimulation?: (code: string, modelPath?: string) => Promise<void>;
  onCodeChange?: (code: string, filePath: string) => void;
  executionOutput?: {
    status: 'idle' | 'running' | 'success' | 'error';
    stdout?: string;
    stderr?: string;
    error?: string;
    timestamp?: string;
  };
}

const SessionIDE = ({
  sessionId = 'session-1',
  workspaceId = 'ws-1',
  enableCollaboration = false,
  onSave,
  onRunSimulation,
  onCodeChange,
  executionOutput
}: Props) => {
  const { user, token } = useAuth();
  const authToken = token || localStorage.getItem('token');
  const [files, setFiles] = useState<FileNode[]>([]);
  const [fileContents, setFileContents] = useState<Record<string, string>>({});
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [layout, setLayout] = useState<'editor-only' | 'with-terminal'>('with-terminal');
  const [terminalHeight, setTerminalHeight] = useState(300); // Height in pixels
  const [isTerminalMinimized, setIsTerminalMinimized] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);
  const [lastBinary, setLastBinary] = useState<string | null>(null);
  const [isLoadingFiles, setIsLoadingFiles] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [autoSaveStatus, setAutoSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [autoSaveError, setAutoSaveError] = useState<string | null>(null);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [showMinimap, setShowMinimap] = useState(true);
  const [editorTheme, setEditorTheme] = useState<'vs-dark-plus' | 'vs-light'>('vs-dark-plus');
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [commandFilter, setCommandFilter] = useState('');
  const [commandSelection, setCommandSelection] = useState(0);
  const [openTabs, setOpenTabs] = useState<string[]>([]);
  const [cursorPosition, setCursorPosition] = useState({ line: 1, column: 1 });
  const [activeActivity, setActiveActivity] = useState('Explorer');
  const [activePanelTab, setActivePanelTab] = useState<PanelTab>('Terminal');
  const [diagnosticCount, setDiagnosticCount] = useState(0);
  const [problems, setProblems] = useState<
    { message: string; severity: monaco.MarkerSeverity; line: number; column: number }[]
  >([]);
  const [extraDirectories, setExtraDirectories] = useState<string[]>([]);
  const extraDirectoriesRef = useRef<string[]>([]);
  const gitDecorationsRef = useRef<string[]>([]);
  const [gitSummary, setGitSummary] = useState<{ added: number; modified: number; deleted: number }>({
    added: 0,
    modified: 0,
    deleted: 0
  });
  const [gitStatus, setGitStatus] = useState<{ path: string; staged: string; unstaged: string }[]>([]);
  const [gitStatusError, setGitStatusError] = useState<string | null>(null);
  const [gitCommitMessage, setGitCommitMessage] = useState('');
  const [gitCommitOutput, setGitCommitOutput] = useState<string | null>(null);
  const [isGitLoading, setIsGitLoading] = useState(false);
  const [debugSession, setDebugSession] = useState<{
    debug_id: string;
    language: 'python' | 'cpp';
    adapter?: string;
    port: number;
    command: string[];
    working_dir: string;
  } | null>(null);
  const [debugError, setDebugError] = useState<string | null>(null);
  const [debugLanguage, setDebugLanguage] = useState<'python' | 'cpp'>('python');
  const [debugTargetPath, setDebugTargetPath] = useState('');
  const [debugArgs, setDebugArgs] = useState('');
  const [debugAdapter, setDebugAdapter] = useState<'gdb' | 'lldb' | ''>('');

  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const ydocRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<WebsocketProvider | null>(null);
  const bindingRef = useRef<MonacoBinding | null>(null);
  const presenceDecorationsRef = useRef<Record<string, string[]>>({});
  const presenceStyleRef = useRef<HTMLStyleElement | null>(null);
  const presencePaletteRef = useRef<Record<string, { cursor: string; selection: string }>>({});
  const awarenessListenerRef = useRef<((...args: any[]) => void) | null>(null);
  const savedContentsRef = useRef<Record<string, string>>({});
  const autoSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);

  const workspacePersistenceEnabled = Boolean(
    workspaceId && !workspaceId.startsWith(PLACEHOLDER_WORKSPACE_PREFIX)
  );

  const toolbarButtonBase: CSSProperties = useMemo(
    () => ({
      background: 'transparent',
      border: '1px solid #3e3e42',
      borderRadius: '6px',
      padding: '0.3rem 0.65rem',
      color: '#d0d0d0',
      cursor: 'pointer',
      fontSize: '0.78rem',
      fontWeight: 500,
      display: 'inline-flex',
      alignItems: 'center',
      gap: '0.35rem',
      lineHeight: 1.2,
      transition: 'background 0.15s ease, border-color 0.15s ease, color 0.15s ease'
    }),
    []
  );

  const layoutButtonStyle = useCallback(
    (active: boolean): CSSProperties => ({
      ...toolbarButtonBase,
      background: active ? '#0e639c' : 'transparent',
      borderColor: active ? '#0e639c' : '#3e3e42',
      color: active ? '#f9fafb' : '#d0d0d0'
    }),
    [toolbarButtonBase]
  );

  const activityItems = useMemo(
    () => [
      { icon: '📁', label: 'Explorer' },
      { icon: '🔍', label: 'Search' },
      { icon: '🔀', label: 'Source Control' },
      { icon: '🐞', label: 'Debug' },
      { icon: '🧩', label: 'Extensions' }
    ],
    []
  );

  const presenceId = useMemo(() => {
    if (user?.id) return user.id;
    const stored = window.localStorage.getItem('cosim-presence-id');
    if (stored) return stored;
    const generated = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `guest-${Date.now()}`;
    window.localStorage.setItem('cosim-presence-id', generated);
    return generated;
  }, [user?.id]);

  const presenceName = useMemo(() => {
    return (
      user?.display_name ||
      user?.full_name ||
      user?.email?.split('@')[0] ||
      user?.email ||
      'Guest'
    );
  }, [user?.display_name, user?.full_name, user?.email]);

  const presenceColor = useMemo(() => {
    let hash = 0;
    for (let i = 0; i < presenceId.length; i += 1) {
      hash = (hash << 5) - hash + presenceId.charCodeAt(i);
      hash |= 0;
    }
    const index = Math.abs(hash) % PRESENCE_COLORS.length;
    return PRESENCE_COLORS[index];
  }, [presenceId]);

  const dirtyTabs = useMemo(() => {
    const dirty = new Set<string>();
    openTabs.forEach(path => {
      if ((fileContents[path] ?? '') !== (savedContentsRef.current[path] ?? '')) {
        dirty.add(path);
      }
    });
    return dirty;
  }, [openTabs, fileContents]);

  const ensurePresenceStyles = useCallback((color: string) => {
    const key = color.replace('#', '').toLowerCase();
    const cached = presencePaletteRef.current[key];
    if (cached) return cached;

    const cursorClass = `presence-cursor-${key}`;
    const selectionClass = `presence-selection-${key}`;
    presencePaletteRef.current[key] = { cursor: cursorClass, selection: selectionClass };

    if (!presenceStyleRef.current) {
      const style = document.createElement('style');
      style.setAttribute('data-presence', 'true');
      document.head.appendChild(style);
      presenceStyleRef.current = style;
    }

    const style = presenceStyleRef.current;
    if (style) {
      style.textContent += `
        .${cursorClass} { border-left: 2px solid ${color} !important; margin-left: -1px; }
        .${selectionClass} { background: ${color}33 !important; }
      `;
    }

    return presencePaletteRef.current[key];
  }, []);

  useEffect(() => {
    if (!selectedFile && openTabs.length > 0) {
      setSelectedFile(openTabs[0]);
    }
    if (selectedFile && openTabs.length > 0 && !openTabs.includes(selectedFile)) {
      setSelectedFile(openTabs[0]);
    }
  }, [openTabs, selectedFile]);

  useEffect(() => {
    const editor = editorRef.current;
    if (editor) {
      const position = editor.getPosition();
      if (position) {
        setCursorPosition({ line: position.lineNumber, column: position.column });
      }
    }
  }, [selectedFile]);

  useEffect(() => {
    extraDirectoriesRef.current = extraDirectories;
  }, [extraDirectories]);

  const handleTabSelect = useCallback((path: string) => {
    setSelectedFile(path);
  }, []);

  const handleTabClose = useCallback(
    (path: string, event?: React.MouseEvent) => {
      if (event) {
        event.stopPropagation();
        event.preventDefault();
      }
      setOpenTabs(prev => {
        const index = prev.indexOf(path);
        const nextTabs = prev.filter(tab => tab !== path);
        if (path === selectedFile) {
          const fallback = nextTabs[index - 1] ?? nextTabs[index] ?? null;
          setSelectedFile(fallback ?? null);
        }
        return nextTabs;
      });
    },
    [selectedFile]
  );

  useEffect(() => {
    const disposables: monaco.IDisposable[] = [];

    type SuggestionConfig = Omit<monaco.languages.CompletionItem, 'range'> & {
      insertTextRules?: monaco.languages.CompletionItemInsertTextRule;
    };

    const registerProvider = (language: string, suggestions: SuggestionConfig[]) => {
      disposables.push(
        monaco.languages.registerCompletionItemProvider(language, {
          triggerCharacters: ['.', ':', '<', ' '],
          provideCompletionItems: (model, position) => {
            const word = model.getWordUntilPosition(position);
            const range: monaco.IRange = {
              startLineNumber: position.lineNumber,
              endLineNumber: position.lineNumber,
              startColumn: word.startColumn,
              endColumn: word.endColumn
            };

            return {
              suggestions: suggestions.map(suggestion => ({
                ...suggestion,
                range
              }))
            };
          }
        })
      );
    };

    registerProvider('python', [
      {
        label: 'print',
        kind: monaco.languages.CompletionItemKind.Function,
        documentation: 'Print a message to stdout.',
        insertText: "print(${1:'Hello CoSim'})",
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
      },
      {
        label: 'async def',
        kind: monaco.languages.CompletionItemKind.Snippet,
        documentation: 'Create an async function scaffold.',
        insertText: 'async def ${1:name}(${2:args}):\n    ${3:pass}\n',
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
      },
      {
        label: 'main guard',
        kind: monaco.languages.CompletionItemKind.Snippet,
        documentation: 'Standard Python __main__ guard pattern.',
        insertText: "if __name__ == '__main__':\n    ${1:main()}\n",
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
      }
    ]);

    registerProvider('cpp', [
      {
        label: 'cout',
        kind: monaco.languages.CompletionItemKind.Snippet,
        documentation: 'Stream output helper.',
        insertText: 'std::cout << ${1:\"Hello CoSim\"} << std::endl;',
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
      },
      {
        label: 'main()',
        kind: monaco.languages.CompletionItemKind.Snippet,
        documentation: 'C++ main function template.',
        insertText: 'int main(int argc, char** argv) {\n    ${1:return 0;}\n}\n',
        insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet
      },
      {
        label: '#include <iostream>',
        kind: monaco.languages.CompletionItemKind.Text,
        documentation: 'Include the iostream header.',
        insertText: '#include <iostream>'
      }
    ]);

    return () => {
      disposables.forEach(disposable => disposable.dispose());
    };
  }, []);

  const normalizedFiles = useCallback((entries: WorkspaceFileDescriptor[]) => {
    return entries.map(entry => ({
      ...entry,
      language: inferLanguage(entry.path, entry.language)
    }));
  }, []);

  const rebuildTreeFromContents = useCallback(
    (contents: Record<string, string>, directories?: string[]) => {
      const descriptors: WorkspaceFileDescriptor[] = Object.entries(contents).map(([path, content]) => ({
        path,
        content,
        language: inferLanguage(path)
      }));
      const targetDirectories = directories ?? extraDirectoriesRef.current;
      setFiles(buildFileTree(normalizedFiles(descriptors), targetDirectories));
    },
    [normalizedFiles]
  );

  const bootstrapFileState = useCallback(
    (entries: WorkspaceFileDescriptor[]) => {
      const normalized = normalizedFiles(entries);
      const contents: Record<string, string> = {};
      normalized.forEach(file => {
        contents[file.path] = file.content;
      });

      savedContentsRef.current = { ...contents };
      setFileContents(contents);
      setFiles(buildFileTree(normalized, extraDirectoriesRef.current));

      const availablePaths = normalized.map(file => file.path);
      const defaultFile = normalized.find(file => file.path.endsWith('.py') || file.path.endsWith('.cpp')) || normalized[0];

      setOpenTabs(prev => {
        const filtered = prev.filter(path => availablePaths.includes(path));
        if (filtered.length > 0) {
          return filtered;
        }
        return defaultFile ? [defaultFile.path] : [];
      });

      setSelectedFile(prev => {
        if (prev && availablePaths.includes(prev)) {
          return prev;
        }
        return defaultFile ? defaultFile.path : null;
      });
    },
    [normalizedFiles]
  );

  useEffect(() => {
    let cancelled = false;

    const initialiseFiles = async () => {
      setIsLoadingFiles(true);
      setLoadError(null);

      const token = localStorage.getItem('token');
      if (!workspacePersistenceEnabled || !token) {
        bootstrapFileState(DEFAULT_FILE_TEMPLATES);
        setIsLoadingFiles(false);
        return;
      }

      try {
        const remoteFiles = await listWorkspaceFiles(token, workspaceId!);

        if (cancelled) return;

        if (remoteFiles.length === 0) {
          bootstrapFileState(DEFAULT_FILE_TEMPLATES);
          await Promise.all(
            DEFAULT_FILE_TEMPLATES.map(file =>
              upsertWorkspaceFile(token, workspaceId!, {
                path: file.path,
                content: file.content,
                language: file.language
              }).catch(() => undefined)
            )
          );
          savedContentsRef.current = DEFAULT_FILE_TEMPLATES.reduce<Record<string, string>>((acc, file) => {
            acc[file.path] = file.content;
            return acc;
          }, {});
          setAutoSaveStatus('saved');
          setLastSavedAt(new Date());
        } else {
          const normalized = remoteFiles.map(file => ({
            path: file.path,
            content: file.content ?? '',
            language: inferLanguage(file.path, file.language ?? undefined)
          }));
          bootstrapFileState(normalized);
          savedContentsRef.current = normalized.reduce<Record<string, string>>((acc, file) => {
            acc[file.path] = file.content;
            return acc;
          }, {});
          setAutoSaveStatus('saved');
          setLastSavedAt(new Date());
        }
      } catch (error) {
        if (cancelled) return;
        console.error('Failed to load workspace files', error);
        setLoadError('Unable to load workspace files. Falling back to defaults.');
        bootstrapFileState(DEFAULT_FILE_TEMPLATES);
        savedContentsRef.current = DEFAULT_FILE_TEMPLATES.reduce<Record<string, string>>((acc, file) => {
          acc[file.path] = file.content;
          return acc;
        }, {});
      } finally {
        if (!cancelled) {
          setIsLoadingFiles(false);
        }
      }
    };

    initialiseFiles();

    return () => {
      cancelled = true;
    };
  }, [bootstrapFileState, workspaceId, workspacePersistenceEnabled]);

  useEffect(() => {
    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, []);

  const currentFile = useMemo(() => {
    const findFile = (nodes: FileNode[]): FileNode | null => {
      for (const node of nodes) {
        if (node.path === selectedFile) return node;
        if (node.children) {
          const found = findFile(node.children);
          if (found) return found;
        }
      }
      return null;
    };
    return findFile(files);
  }, [files, selectedFile]);

  const currentContent = selectedFile ? fileContents[selectedFile] ?? '' : '';
  const currentLanguage: SupportedLanguage = currentFile?.language
    ? currentFile.language
    : inferLanguage(selectedFile || '');
  const isDirty = useMemo(() => {
    if (!selectedFile) return false;
    return (fileContents[selectedFile] ?? '') !== (savedContentsRef.current[selectedFile] ?? '');
  }, [fileContents, selectedFile]);
  const breadcrumbs = useMemo(() => (selectedFile ? selectedFile.split('/').filter(Boolean) : []), [selectedFile]);
  const isDarkTheme = editorTheme !== 'vs-light';
  const wordWrapMode: monaco.editor.IEditorOptions['wordWrap'] = 'on';
  const activityButtonStyle: CSSProperties = {
    width: 36,
    height: 36,
    borderRadius: '8px',
    border: 'none',
    background: 'transparent',
    color: '#9ca3af',
    cursor: 'pointer',
    fontSize: '1.1rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s ease, color 0.15s ease'
  };

  const tabStyle = useCallback(
    (active: boolean): CSSProperties => ({
      display: 'flex',
      alignItems: 'center',
      gap: '0.45rem',
      padding: '0.45rem 0.85rem',
      cursor: 'pointer',
      backgroundColor: active ? '#1e1e1e' : '#2b2b2b',
      color: active ? '#f8fafc' : '#d1d5db',
      borderRight: '1px solid #3a3a3a',
      borderBottom: active ? '2px solid #007acc' : '2px solid transparent',
      borderTop: '1px solid #3a3a3a',
      position: 'relative',
      maxWidth: 220,
      minWidth: 120,
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }),
    []
  );

  const tabCloseButtonStyle: CSSProperties = {
    border: 'none',
    background: 'transparent',
    color: '#9ca3af',
    cursor: 'pointer',
    fontSize: '0.75rem',
    lineHeight: 1,
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center'
  };

  const autoSaveSummary = useMemo(() => {
    switch (autoSaveStatus) {
      case 'saving':
        return 'Auto Save: Saving…';
      case 'saved':
        return 'Auto Save: Saved';
      case 'error':
        return 'Auto Save: Error';
      default:
        return 'Auto Save: Idle';
    }
  }, [autoSaveStatus]);

  const statusLeft = useMemo(
    () => [
      `Ln ${cursorPosition.line}, Col ${cursorPosition.column}`,
      'Spaces: 4',
      'UTF-8',
      'LF',
      currentLanguage ? currentLanguage.toUpperCase() : undefined
    ].filter(Boolean) as string[],
    [cursorPosition, currentLanguage]
  );

  const gitDecorationStyles = `
    .git-added-gutter { border-left: 3px solid #81b88b !important; }
    .git-modified-gutter { border-left: 3px solid #d7ba7d !important; }
    .git-deleted-gutter { border-left: 3px solid #c74e39 !important; }
  `;

  useEffect(() => {
    const editor = editorRef.current;
    const model = editor?.getModel();
    if (!editor || !model) return;
    const markers = monaco.editor.getModelMarkers({ resource: model.uri });
    setDiagnosticCount(markers.length);
    setProblems(
      markers.map(marker => ({
        message: marker.message,
        severity: marker.severity,
        line: marker.startLineNumber,
        column: marker.startColumn
      }))
    );
  }, [selectedFile]);

  const computeLineDiff = useCallback((base: string, current: string) => {
    const baseLines = base.split(/\r?\n/);
    const currentLines = current.split(/\r?\n/);
    const maxLen = Math.max(baseLines.length, currentLines.length);
    const added: number[] = [];
    const deleted: number[] = [];
    const modified: number[] = [];

    for (let i = 0; i < maxLen; i++) {
      const baseLine = baseLines[i];
      const currLine = currentLines[i];
      if (baseLine === undefined && currLine !== undefined) {
        added.push(i + 1);
      } else if (currLine === undefined && baseLine !== undefined) {
        deleted.push(Math.max(1, i));
      } else if (baseLine !== currLine) {
        modified.push(i + 1);
      }
    }

    return { added, deleted, modified };
  }, []);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || !selectedFile) return;
    const saved = savedContentsRef.current[selectedFile] ?? '';
    const { added, modified, deleted } = computeLineDiff(saved, currentContent);
    setGitSummary({ added: added.length, modified: modified.length, deleted: deleted.length });

    const decorations: monaco.editor.IModelDeltaDecoration[] = [];
    added.forEach(line => {
      decorations.push({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          linesDecorationsClassName: 'git-added-gutter',
          overviewRuler: { color: '#81b88b', position: monaco.editor.OverviewRulerLane.Left }
        }
      });
    });
    modified.forEach(line => {
      decorations.push({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          linesDecorationsClassName: 'git-modified-gutter',
          overviewRuler: { color: '#d7ba7d', position: monaco.editor.OverviewRulerLane.Left }
        }
      });
    });
    deleted.forEach(line => {
      const targetLine = Math.min(line, Math.max(1, editor.getModel()?.getLineCount() ?? 1));
      decorations.push({
        range: new monaco.Range(targetLine, 1, targetLine, 1),
        options: {
          isWholeLine: true,
          linesDecorationsClassName: 'git-deleted-gutter',
          overviewRuler: { color: '#c74e39', position: monaco.editor.OverviewRulerLane.Left }
        }
      });
    });

    gitDecorationsRef.current = editor.deltaDecorations(gitDecorationsRef.current, decorations);
  }, [computeLineDiff, currentContent, selectedFile]);

  const commands = useMemo(
    () => [
      {
        id: 'toggle-theme',
        label: isDarkTheme ? 'Switch to Light Theme' : 'Switch to Dark+ Theme',
        detail: 'Appearance'
      },
      {
        id: 'toggle-minimap',
        label: showMinimap ? 'Disable Minimap' : 'Enable Minimap',
        detail: 'View'
      },
      {
        id: 'format-document',
        label: 'Format Document',
        detail: 'Editor'
      },
      {
        id: 'toggle-word-wrap',
        label: `Word Wrap: ${wordWrapMode === 'on' ? 'On' : 'Off'}`,
        detail: 'Editor'
      },
      {
        id: 'save-file',
        label: 'Save',
        detail: 'File'
      },
      {
        id: 'rename-symbol',
        label: 'Rename Symbol',
        detail: 'Refactor'
      },
      {
        id: 'go-to-definition',
        label: 'Go to Definition',
        detail: 'Navigation'
      },
      {
        id: 'peek-definition',
        label: 'Peek Definition',
        detail: 'Navigation'
      },
      {
        id: 'find-references',
        label: 'Find References',
        detail: 'Navigation'
      },
      {
        id: 'go-to-symbol',
        label: 'Go to Symbol in File…',
        detail: 'Navigation'
      },
      {
        id: 'go-to-line',
        label: 'Go to Line…',
        detail: 'Navigation'
      },
      {
        id: 'find',
        label: 'Find',
        detail: 'Edit'
      },
      {
        id: 'replace',
        label: 'Replace',
        detail: 'Edit'
      },
      {
        id: 'quick-fix',
        label: 'Quick Fix…',
        detail: 'Code Actions'
      },
      {
        id: 'open-problems',
        label: `View Problems (${diagnosticCount})`,
        detail: 'Panels'
      },
      {
        id: 'open-output',
        label: 'Show Output Panel',
        detail: 'Panels'
      },
      {
        id: 'open-terminal',
        label: layout === 'with-terminal' ? 'Focus Terminal/Panel' : 'Open Terminal Panel',
        detail: 'Panels'
      },
      {
        id: 'toggle-terminal',
        label: 'Toggle Integrated Terminal',
        detail: 'Panels'
      },
      {
        id: 'toggle-line-comment',
        label: 'Toggle Line Comment',
        detail: 'Edit'
      },
      {
        id: 'add-next-occurrence',
        label: 'Add Selection to Next Find Match',
        detail: 'Multi-cursor'
      }
    ],
    [diagnosticCount, isDarkTheme, layout, showMinimap, wordWrapMode]
  );
  const filteredCommands = useMemo(() => {
    const query = commandFilter.trim().toLowerCase();
    if (!query) return commands;
    return commands.filter(cmd => cmd.label.toLowerCase().includes(query) || cmd.detail.toLowerCase().includes(query));
  }, [commandFilter, commands]);

  useEffect(() => {
    if (showCommandPalette) {
      setCommandSelection(0);
    }
  }, [showCommandPalette]);

  const statusRight = useMemo(
    () => [
      autoSaveSummary,
      `Problems: ${diagnosticCount}`,
      `Git: +${gitSummary.added} ~${gitSummary.modified} -${gitSummary.deleted}`,
      showMinimap ? 'Minimap On' : 'Minimap Off',
      isDarkTheme ? 'Dark Theme' : 'Light Theme',
      workspaceId ? `Workspace ${workspaceId}` : undefined,
      sessionId ? `Session ${sessionId}` : undefined
    ].filter(Boolean) as string[],
    [autoSaveSummary, diagnosticCount, gitSummary, showMinimap, isDarkTheme, workspaceId, sessionId]
  );

  useEffect(() => {
    return () => {
      if (providerRef.current && awarenessListenerRef.current) {
        providerRef.current.awareness.off('change', awarenessListenerRef.current);
        awarenessListenerRef.current = null;
      }
      if (editorRef.current) {
        const decorationIds = Object.values(presenceDecorationsRef.current).flat();
        if (decorationIds.length > 0) {
          editorRef.current.deltaDecorations(decorationIds, []);
        }
        presenceDecorationsRef.current = {};
      }
      if (bindingRef.current) {
        try {
          bindingRef.current.destroy();
        } catch (error) {
          console.warn('Failed to dispose Monaco binding', error);
        }
        bindingRef.current = null;
      }
      if (providerRef.current) {
        try {
          providerRef.current.destroy();
        } catch (error) {
          console.warn('Failed to dispose Yjs provider', error);
        }
        providerRef.current = null;
      }
      if (ydocRef.current) {
        try {
          ydocRef.current.destroy();
        } catch (error) {
          console.warn('Failed to dispose Yjs document', error);
        }
        ydocRef.current = null;
      }
    };
  }, [selectedFile]);

  const handleChange: OnChange = (value) => {
    if (selectedFile && value !== undefined) {
      setFileContents(prev => ({
        ...prev,
        [selectedFile]: value
      }));
      setAutoSaveStatus('idle');
      setAutoSaveError(null);
    }
  };

  const handleFileSelect = (file: FileNode) => {
    if (file.type === 'file') {
      setSelectedFile(file.path);
      setOpenTabs(prev => (prev.includes(file.path) ? prev : [...prev, file.path]));
    }
  };

  const getErrorMessage = (error: unknown): string => {
    if (error instanceof Error && error.message) return error.message;
    return 'Unexpected error';
  };

  const persistFile = useCallback(
    async (path: string, content: string, { skipStatusUpdate = false } = {}) => {
      if (!workspacePersistenceEnabled) return;

      const token = localStorage.getItem('token');
      if (!token) return;

      if (content === savedContentsRef.current[path]) {
        if (!skipStatusUpdate) {
          setAutoSaveStatus('saved');
          setLastSavedAt(new Date());
        }
        return;
      }

      if (!skipStatusUpdate) {
        setAutoSaveStatus('saving');
        setAutoSaveError(null);
      }

      try {
        await upsertWorkspaceFile(token, workspaceId!, {
          path,
          content,
          language: inferLanguage(path)
        });
        savedContentsRef.current[path] = content;
        setAutoSaveStatus('saved');
        setLastSavedAt(new Date());
      } catch (error) {
        console.error('Failed to persist file', error);
        setAutoSaveStatus('error');
        setAutoSaveError(getErrorMessage(error));
      }
    },
    [workspaceId, workspacePersistenceEnabled]
  );

  const refreshGitStatus = useCallback(async () => {
    if (!workspacePersistenceEnabled || !authToken || !workspaceId) return;
    setIsGitLoading(true);
    setGitStatusError(null);
    try {
      const response = await getGitStatus(authToken, workspaceId);
      setGitStatus(response.entries);
    } catch (error) {
      console.error('Failed to fetch git status', error);
      setGitStatusError(getErrorMessage(error));
    } finally {
      setIsGitLoading(false);
    }
  }, [authToken, getErrorMessage, workspaceId, workspacePersistenceEnabled]);

  useEffect(() => {
    if (isLoadingFiles) return;
    if (!workspacePersistenceEnabled) return;
    if (!selectedFile) return;

    const content = currentContent;
    if (content === savedContentsRef.current[selectedFile]) {
      return;
    }

    if (autoSaveTimerRef.current) {
      clearTimeout(autoSaveTimerRef.current);
    }

    autoSaveTimerRef.current = setTimeout(() => {
      void persistFile(selectedFile, content);
    }, AUTO_SAVE_INTERVAL_MS);

    return () => {
      if (autoSaveTimerRef.current) {
        clearTimeout(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, [currentContent, selectedFile, persistFile, workspacePersistenceEnabled, isLoadingFiles]);

  useEffect(() => {
    if (activeActivity === 'Source Control') {
      void refreshGitStatus();
    }
  }, [activeActivity, refreshGitStatus]);

  // Notify parent of code changes for simulation
  useEffect(() => {
    if (selectedFile && selectedFile.endsWith('.py') && onCodeChange) {
      const code = fileContents[selectedFile] || '';
      onCodeChange(code, selectedFile);
    }
  }, [selectedFile, fileContents, onCodeChange]);

const handleSave = useCallback(async () => {
  if (!selectedFile) return;
  const content = fileContents[selectedFile] ?? '';
  await persistFile(selectedFile, content, { skipStatusUpdate: false });
  onSave?.({ path: selectedFile, content });
}, [fileContents, onSave, persistFile, selectedFile]);

const executeCommand = useCallback(
  (id: string) => {
      switch (id) {
        case 'toggle-theme':
          setEditorTheme(prev => (prev === 'vs-light' ? 'vs-dark-plus' : 'vs-light'));
          break;
        case 'toggle-minimap':
          setShowMinimap(prev => !prev);
          break;
        case 'format-document':
          editorRef.current?.getAction('editor.action.formatDocument')?.run();
          break;
        case 'toggle-word-wrap':
          // wordWrap is fixed to on in current config
          break;
        case 'save-file':
          void handleSave();
          break;
        case 'rename-symbol':
          editorRef.current?.getAction('editor.action.rename')?.run();
          break;
        case 'go-to-definition':
          editorRef.current?.getAction('editor.action.revealDefinition')?.run();
          break;
        case 'peek-definition':
          editorRef.current?.getAction('editor.action.peekDefinition')?.run();
          break;
        case 'find-references':
          editorRef.current?.getAction('editor.action.referenceSearch.trigger')?.run();
          break;
        case 'go-to-symbol':
          editorRef.current?.getAction('editor.action.quickOutline')?.run();
          break;
        case 'go-to-line':
          editorRef.current?.getAction('editor.action.gotoLine')?.run();
          break;
        case 'find':
          editorRef.current?.getAction('actions.find')?.run();
          break;
        case 'replace':
          editorRef.current?.getAction('editor.action.startFindReplaceAction')?.run();
          break;
        case 'quick-fix':
          editorRef.current?.getAction('editor.action.quickFix')?.run();
          break;
        case 'open-problems':
          setLayout('with-terminal');
          setIsTerminalMinimized(false);
          setActivePanelTab('Problems');
          break;
        case 'open-output':
          setLayout('with-terminal');
          setIsTerminalMinimized(false);
          setActivePanelTab('Output');
          break;
        case 'open-terminal':
          setLayout('with-terminal');
          setIsTerminalMinimized(false);
          setActivePanelTab('Terminal');
          break;
        case 'toggle-terminal':
          setLayout(prev => (prev === 'with-terminal' ? 'editor-only' : 'with-terminal'));
          setIsTerminalMinimized(false);
          setActivePanelTab('Terminal');
          break;
        case 'toggle-line-comment':
          editorRef.current?.getAction('editor.action.commentLine')?.run();
          break;
        case 'add-next-occurrence':
          editorRef.current?.getAction('editor.action.addSelectionToNextFindMatch')?.run();
          break;
    default:
      break;
  }
  setShowCommandPalette(false);
},
[handleSave]
);

  useEffect(() => {
    if (!showCommandPalette) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (!showCommandPalette) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        setShowCommandPalette(false);
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setCommandSelection(prev => {
          if (filteredCommands.length === 0) return 0;
          return (prev + 1) % filteredCommands.length;
        });
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setCommandSelection(prev => {
          if (filteredCommands.length === 0) return 0;
          return (prev - 1 + filteredCommands.length) % filteredCommands.length;
        });
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        const chosen = filteredCommands[commandSelection];
        if (chosen) {
          executeCommand(chosen.id);
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [commandSelection, executeCommand, filteredCommands, showCommandPalette]);

  const handleEditorMount: OnMount = useCallback(
    (editor, monacoInstance) => {
      editorRef.current = editor;

      // VS Code-like Dark+ theme for Monaco
      monacoInstance.editor.defineTheme('vs-dark-plus', darkPlusTheme);

      // Enable advanced Monaco editor features
      monacoInstance.languages.typescript.typescriptDefaults.setCompilerOptions({
        target: monacoInstance.languages.typescript.ScriptTarget.Latest,
        allowNonTsExtensions: true,
        moduleResolution: monacoInstance.languages.typescript.ModuleResolutionKind.NodeJs,
        module: monacoInstance.languages.typescript.ModuleKind.CommonJS,
        noEmit: true,
        esModuleInterop: true,
        jsx: monacoInstance.languages.typescript.JsxEmit.React,
        allowJs: true,
        typeRoots: ['node_modules/@types']
      });

      // Configure Python-like language features
      monacoInstance.languages.registerCompletionItemProvider('python', {
        provideCompletionItems: (model, position) => {
          const word = model.getWordUntilPosition(position);
          const range = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn
          };

          const suggestions: monaco.languages.CompletionItem[] = [
            // Python built-ins
            { label: 'print', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'print(${1:object})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Print objects to the text stream', range },
            { label: 'len', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'len(${1:object})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Return the length of an object', range },
            { label: 'range', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'range(${1:stop})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Return a sequence of numbers', range },
            { label: 'enumerate', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'enumerate(${1:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Return an enumerate object', range },
            { label: 'zip', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'zip(${1:iterables})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Zip iterables together', range },
            { label: 'map', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'map(${1:function}, ${2:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Apply function to every item', range },
            { label: 'filter', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'filter(${1:function}, ${2:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Filter iterable', range },
            { label: 'sorted', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'sorted(${1:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Return a sorted list', range },
            { label: 'sum', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'sum(${1:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Sum of items', range },
            { label: 'min', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'min(${1:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Return minimum value', range },
            { label: 'max', kind: monacoInstance.languages.CompletionItemKind.Function, insertText: 'max(${1:iterable})', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Return maximum value', range },
            
            // Python keywords/snippets
            { label: 'for', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'for ${1:item} in ${2:iterable}:\n\t${3:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'For loop', range },
            { label: 'while', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'while ${1:condition}:\n\t${2:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'While loop', range },
            { label: 'if', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'if ${1:condition}:\n\t${2:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'If statement', range },
            { label: 'def', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'def ${1:function_name}(${2:params}):\n\t"""${3:docstring}"""\n\t${4:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Define function', range },
            { label: 'class', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'class ${1:ClassName}:\n\t"""${2:docstring}"""\n\t\n\tdef __init__(self, ${3:params}):\n\t\t${4:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Define class', range },
            { label: 'try', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'try:\n\t${1:pass}\nexcept ${2:Exception} as ${3:e}:\n\t${4:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Try-except block', range },
            { label: 'with', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'with ${1:expression} as ${2:variable}:\n\t${3:pass}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'With statement', range },
            
            // Common libraries
            { label: 'import numpy as np', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'import numpy as np', documentation: 'Import NumPy', range },
            { label: 'import pandas as pd', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'import pandas as pd', documentation: 'Import Pandas', range },
            { label: 'import matplotlib.pyplot as plt', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'import matplotlib.pyplot as plt', documentation: 'Import Matplotlib', range },
          ];

          return { suggestions };
        }
      });

      // Configure C++ completions
      monacoInstance.languages.registerCompletionItemProvider('cpp', {
        provideCompletionItems: (model, position) => {
          const word = model.getWordUntilPosition(position);
          const range = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn
          };

          const suggestions: monaco.languages.CompletionItem[] = [
            // STL containers
            { label: 'std::vector', kind: monacoInstance.languages.CompletionItemKind.Class, insertText: 'std::vector<${1:T}>', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Dynamic array', range },
            { label: 'std::string', kind: monacoInstance.languages.CompletionItemKind.Class, insertText: 'std::string', documentation: 'String class', range },
            { label: 'std::map', kind: monacoInstance.languages.CompletionItemKind.Class, insertText: 'std::map<${1:Key}, ${2:Value}>', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Sorted associative container', range },
            { label: 'std::unordered_map', kind: monacoInstance.languages.CompletionItemKind.Class, insertText: 'std::unordered_map<${1:Key}, ${2:Value}>', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Hash table', range },
            { label: 'std::set', kind: monacoInstance.languages.CompletionItemKind.Class, insertText: 'std::set<${1:T}>', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Sorted set', range },
            { label: 'std::cout', kind: monacoInstance.languages.CompletionItemKind.Variable, insertText: 'std::cout << ${1:value} << std::endl;', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Console output', range },
            { label: 'std::endl', kind: monacoInstance.languages.CompletionItemKind.Variable, insertText: 'std::endl', documentation: 'End line', range },
            
            // Common snippets
            { label: 'for', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'for (${1:int} ${2:i} = 0; ${2:i} < ${3:n}; ++${2:i}) {\n\t${4:// body}\n}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'For loop', range },
            { label: 'while', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'while (${1:condition}) {\n\t${2:// body}\n}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'While loop', range },
            { label: 'if', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'if (${1:condition}) {\n\t${2:// body}\n}', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'If statement', range },
            { label: 'class', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'class ${1:ClassName} {\npublic:\n\t${1:ClassName}();\n\t~${1:ClassName}();\n\nprivate:\n\t${2:// members}\n};', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Class definition', range },
            { label: 'struct', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: 'struct ${1:StructName} {\n\t${2:// members}\n};', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Struct definition', range },
            { label: '#include', kind: monacoInstance.languages.CompletionItemKind.Snippet, insertText: '#include <${1:header}>', insertTextRules: monacoInstance.languages.CompletionItemInsertTextRule.InsertAsSnippet, documentation: 'Include header', range },
          ];

          return { suggestions };
        }
      });

      // Enable parameter hints
      editor.updateOptions({
        parameterHints: { enabled: true },
        suggestOnTriggerCharacters: true,
        quickSuggestions: {
          other: true,
          comments: false,
          strings: false
        },
        wordBasedSuggestions: 'allDocuments',
        suggest: {
          showKeywords: true,
          showSnippets: true,
          showClasses: true,
          showFunctions: true,
          showVariables: true,
          showMethods: true,
          showProperties: true
        }
      });

      const updateMarkers = () => {
        const currentModel = editor.getModel();
        if (!currentModel) return;
        const markers = monacoInstance.editor.getModelMarkers({ resource: currentModel.uri });
        setDiagnosticCount(markers.length);
        setProblems(
          markers.map(marker => ({
            message: marker.message,
            severity: marker.severity,
            line: marker.startLineNumber,
            column: marker.startColumn
          }))
        );
      };

      updateMarkers();

      // Enable collaboration if configured
      if (enableCollaboration && selectedFile) {
        const ydoc = new Y.Doc();
        ydocRef.current = ydoc;

        const collabUrl = import.meta.env.VITE_COLLAB_WS_URL || 'ws://localhost:1234';
        const provider = new WebsocketProvider(collabUrl, `${workspaceId}:${selectedFile}`, ydoc);
        providerRef.current = provider;

        const ytext = ydoc.getText('monaco');
        const binding = new MonacoBinding(ytext, editor.getModel()!, new Set([editor]), provider.awareness);
        bindingRef.current = binding;

        const awareness = provider.awareness;
        awareness.setLocalStateField('user', {
          id: presenceId,
          name: presenceName,
          color: presenceColor
        });

        const applyPresenceDecorations = () => {
          const editorInstance = editorRef.current;
          if (!editorInstance) return;

          const nextDecorations: Record<string, string[]> = {};
          awareness.getStates().forEach((state, clientId) => {
            const userState = (state as any)?.user as { id?: string; name?: string; color?: string } | undefined;
            const cursorState = (state as any)?.cursor as
              | { anchor?: { line: number; column: number }; head?: { line: number; column: number } }
              | undefined;
            if (!userState || !cursorState) return;
            if (userState.id === presenceId) return;

            const anchor = cursorState.anchor;
            const head = cursorState.head;
            if (!anchor || !head) return;

            const isForward =
              anchor.line < head.line || (anchor.line === head.line && anchor.column <= head.column);
            const start = isForward ? anchor : head;
            const end = isForward ? head : anchor;

            const classes = ensurePresenceStyles(userState.color || '#f59e0b');
            const decorations: monaco.editor.IModelDeltaDecoration[] = [];

            if (start.line !== end.line || start.column !== end.column) {
              decorations.push({
                range: new monaco.Range(start.line, start.column, end.line, end.column),
                options: {
                  className: classes.selection,
                  stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges
                }
              });
            }

            decorations.push({
              range: new monaco.Range(head.line, head.column, head.line, head.column),
              options: {
                className: classes.cursor,
                hoverMessage: { value: userState.name || 'Collaborator' },
                stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges
              }
            });

            const key = String(clientId);
            const previous = presenceDecorationsRef.current[key] || [];
            nextDecorations[key] = editorInstance.deltaDecorations(previous, decorations);
          });

          Object.keys(presenceDecorationsRef.current).forEach(clientId => {
            if (!nextDecorations[clientId]) {
              editorRef.current?.deltaDecorations(presenceDecorationsRef.current[clientId], []);
            }
          });

          presenceDecorationsRef.current = nextDecorations;
        };

        const awarenessChangeHandler = () => applyPresenceDecorations();
        awareness.on('change', awarenessChangeHandler);
        awarenessListenerRef.current = awarenessChangeHandler;
        applyPresenceDecorations();

        let presenceUpdateHandle: number | null = null;
        const schedulePresenceUpdate = (selection: monaco.Selection) => {
          if (presenceUpdateHandle) {
            window.clearTimeout(presenceUpdateHandle);
          }
          presenceUpdateHandle = window.setTimeout(() => {
            awareness.setLocalStateField('cursor', {
              anchor: { line: selection.startLineNumber, column: selection.startColumn },
              head: { line: selection.endLineNumber, column: selection.endColumn }
            });
            presenceUpdateHandle = null;
          }, 50);
        };

        const selectionDisposable = editor.onDidChangeCursorSelection(event => {
          schedulePresenceUpdate(event.selection);
        });

        const initialSelection = editor.getSelection();
        if (initialSelection) {
          schedulePresenceUpdate(initialSelection);
        }

        editor.onDidDispose(() => {
          selectionDisposable.dispose();
          if (presenceUpdateHandle) {
            window.clearTimeout(presenceUpdateHandle);
          }
        });
      }

      // Add keyboard shortcuts
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyS, () => {
        void handleSave();
      });
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyMod.Shift | monacoInstance.KeyCode.KeyP, () => {
        setShowCommandPalette(true);
        setCommandFilter('');
      });
      editor.addCommand(monacoInstance.KeyMod.Shift | monacoInstance.KeyMod.Alt | monacoInstance.KeyCode.KeyF, () => {
        editor.getAction('editor.action.formatDocument')?.run();
      });
      editor.addCommand(monacoInstance.KeyCode.F2, () => {
        editor.getAction('editor.action.rename')?.run();
      });
      editor.addCommand(monacoInstance.KeyCode.F12, () => {
        editor.getAction('editor.action.revealDefinition')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.Alt | monacoInstance.KeyCode.F12, () => {
        editor.getAction('editor.action.peekDefinition')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.Shift | monacoInstance.KeyCode.F12, () => {
        editor.getAction('editor.action.referenceSearch.trigger')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.Slash, () => {
        editor.getAction('editor.action.commentLine')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.KeyD, () => {
        editor.getAction('editor.action.addSelectionToNextFindMatch')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyMod.Shift | monacoInstance.KeyCode.KeyP, () => {
        setShowCommandPalette(true);
        setCommandFilter('');
      });
      editor.addCommand(monacoInstance.KeyMod.Shift | monacoInstance.KeyMod.Alt | monacoInstance.KeyCode.KeyF, () => {
        editor.getAction('editor.action.formatDocument')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.Period, () => {
        editor.getAction('editor.action.quickFix')?.run();
      });
      editor.addCommand(monacoInstance.KeyCode.F8, () => {
        editor.getAction('editor.action.marker.next')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.Shift | monacoInstance.KeyCode.F8, () => {
        editor.getAction('editor.action.marker.prev')?.run();
      });
      editor.addCommand(monacoInstance.KeyMod.CtrlCmd | monacoInstance.KeyCode.Backquote, () => {
        setLayout(prev => (prev === 'with-terminal' ? 'editor-only' : 'with-terminal'));
        setIsTerminalMinimized(false);
        setActivePanelTab('Terminal');
      });

      const cursorDisposable = editor.onDidChangeCursorPosition(event => {
        setCursorPosition({ line: event.position.lineNumber, column: event.position.column });
      });

      const markerDisposable = monacoInstance.editor.onDidChangeMarkers(changed => {
        const currentModel = editor.getModel();
        if (!currentModel) return;
        if (changed.some(uri => uri.toString() === currentModel.uri.toString())) {
          updateMarkers();
        }
      });

      editor.onDidDispose(() => {
        cursorDisposable.dispose();
        markerDisposable.dispose();
      });

      const initialPosition = editor.getPosition();
      if (initialPosition) {
        setCursorPosition({ line: initialPosition.lineNumber, column: initialPosition.column });
      }
    },
    [enableCollaboration, ensurePresenceStyles, handleSave, presenceColor, presenceId, presenceName, selectedFile, workspaceId]
  );

  const handleRunPython = async () => {
    if (!selectedFile || !selectedFile.endsWith('.py')) {
      console.error('Please select a Python file');
      return;
    }

    setIsExecuting(true);
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.warn('No authentication token found - running without auth');
      }

      await handleSave();

      // Debug: Check what we have
      console.log('🔍 Debug info:', {
        selectedFile,
        hasEditorRef: !!editorRef.current,
        editorValue: editorRef.current?.getValue()?.substring(0, 100),
        fileContentsKeys: Object.keys(fileContents),
        fileContentsForSelected: fileContents[selectedFile]?.substring(0, 100),
      });

      // Get code directly from Monaco editor to ensure we have the latest content
      const code = editorRef.current?.getValue() ?? fileContents[selectedFile] ?? '';
      console.log('📝 Code to execute (length):', code.length, 'First 100 chars:', code.substring(0, 100));
      
      // If onRunSimulation prop is provided, use it (simulation mode)
      if (onRunSimulation) {
        console.log('🎮 Running Python in simulator:', selectedFile);
        
        // Find model files in workspace
        const xmlFiles = Object.keys(fileContents).filter(path => path.endsWith('.xml'));
        const urdfFiles = Object.keys(fileContents).filter(path => path.endsWith('.urdf'));
        const modelPath = xmlFiles.length > 0 ? xmlFiles[0] : urdfFiles.length > 0 ? urdfFiles[0] : undefined;
        
        if (modelPath) {
          console.log('📦 Using model from workspace:', modelPath);
        }
        
        await onRunSimulation(code, modelPath);
      } else {
        // Fallback to old executePython API
        console.log('🐍 Running Python (legacy mode):', selectedFile);
        if (token) {
          await executePython(token, sessionId, code, selectedFile);
        } else {
          console.log('Code:', code);
        }
      }
    } catch (error) {
      console.error('Failed to execute Python:', error);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleBuildCpp = async () => {
    if (!selectedFile || !selectedFile.endsWith('.cpp')) {
      console.error('Please select a C++ file');
      return;
    }

    setIsBuilding(true);
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.error('No authentication token found');
        return;
      }

      await handleSave();

      const fileName = selectedFile.split('/').pop()!;
      const outputBinary = `/workspace/build/${fileName.replace('.cpp', '')}`;

      console.log('🔨 Building C++:', selectedFile);
      await buildCpp(token, sessionId, [selectedFile], outputBinary, 'g++', ['-std=c++17', '-O2', '-Wall']);

      setLastBinary(outputBinary);
      console.log('✓ Build successful:', outputBinary);
    } catch (error) {
      console.error('Build failed:', error);
      setLastBinary(null);
    } finally {
      setIsBuilding(false);
    }
  };

  const handleRunBinary = async () => {
    if (!lastBinary) {
      console.error('No compiled binary available. Build first.');
      return;
    }

    setIsExecuting(true);
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.error('No authentication token found');
        return;
      }

      console.log('▶️  Running binary:', lastBinary);
      await executeBinary(token, sessionId, lastBinary);
    } catch (error) {
      console.error('Failed to execute binary:', error);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleRunInSimulator = async () => {
    if (!selectedFile || !selectedFile.endsWith('.py')) {
      console.error('Please select a Python control script');
      return;
    }

    try {
      const token = localStorage.getItem('token');
      if (!token) {
        console.error('No authentication token found');
        return;
      }

      await handleSave();

      const code = fileContents[selectedFile] ?? '';
      
      // Find MuJoCo XML model files in workspace
      const xmlFiles = Object.keys(fileContents).filter(path => path.endsWith('.xml'));
      const modelPath = xmlFiles.length > 0 ? xmlFiles[0] : undefined;

      console.log('🎮 Running in simulator:', selectedFile);
      if (modelPath) {
        console.log('📦 Using model:', modelPath);
      }

      // Call simulation agent API
      const simulationApiUrl = import.meta.env.VITE_SIMULATION_API_URL || 'http://localhost:8005';
      
      // First, ensure simulation exists
      const sessionIdForSim = sessionId || 'default-session';
      
      try {
        // Try to create simulation if it doesn't exist
        await fetch(`${simulationApiUrl}/simulations/create`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({
            session_id: sessionIdForSim,
            engine: 'mujoco',
            model_path: modelPath || '/app/models/cartpole.xml', // Default model
            width: 800,
            height: 600,
            fps: 60,
            headless: true,
          }),
        });
      } catch (error) {
        console.log('Simulation may already exist, continuing...');
      }

      // Execute code in simulation context
      const response = await fetch(`${simulationApiUrl}/simulations/${sessionIdForSim}/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          code,
          model_path: modelPath,
          working_dir: '/workspace',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Simulation execution failed');
      }

      const result = await response.json();
      
      console.log('✓ Simulation execution completed');
      console.log('📊 stdout:', result.stdout);
      if (result.stderr) {
        console.error('⚠️  stderr:', result.stderr);
      }
      if (result.error) {
        console.error('❌ Error:', result.error);
      }

      // Display results in terminal (if available)
      // TODO: Send results to terminal component

    } catch (error) {
      console.error('Failed to run in simulator:', error);
    }
  };

  const handleBuildAndRun = async () => {
    await handleBuildCpp();
    setTimeout(() => {
      if (lastBinary) {
        void handleRunBinary();
      }
    }, 1000);
  };

  const handleTerminalCommand = (command: string) => {
    console.log('Terminal command:', command);
  };

  const handleFormatDocument = useCallback(() => {
    if (!editorRef.current) return;
    const formatAction = editorRef.current.getAction('editor.action.formatDocument');
    formatAction?.run();
  }, []);

  const handleThemeToggle = useCallback(() => {
    setEditorTheme(prev => (prev === 'vs-light' ? 'vs-dark-plus' : 'vs-light'));
  }, []);

  const handleMinimapToggle = useCallback(() => {
    setShowMinimap(prev => !prev);
  }, []);

  const handleCreatePath = useCallback(
    (parentPath: string, name: string, type: 'file' | 'directory') => {
      const safeName = name || (type === 'file' ? 'untitled' : 'new-folder');
      const normalizedParent = parentPath === '/' ? '' : parentPath;
      const newPath = `${normalizedParent}/${safeName}`;

      if (type === 'file') {
        setFileContents(prev => {
          if (prev[newPath]) return prev;
          const next = { ...prev, [newPath]: '' };
          savedContentsRef.current = { ...savedContentsRef.current, [newPath]: '' };
          rebuildTreeFromContents(next, extraDirectories);
          return next;
        });
        setOpenTabs(prev => (prev.includes(newPath) ? prev : [...prev, newPath]));
        setSelectedFile(newPath);
        if (workspacePersistenceEnabled && authToken && workspaceId) {
          void upsertWorkspaceFile(authToken, workspaceId, {
            path: newPath,
            content: '',
            language: inferLanguage(newPath)
          }).catch(error => {
            console.error('Failed to create file', error);
            setAutoSaveStatus('error');
            setAutoSaveError(getErrorMessage(error));
          });
        }
      } else {
        setExtraDirectories(prev => {
          const nextDirs = Array.from(new Set([...prev, newPath]));
          rebuildTreeFromContents(fileContents, nextDirs);
          return nextDirs;
        });
      }
    },
    [authToken, extraDirectories, fileContents, getErrorMessage, rebuildTreeFromContents, workspaceId, workspacePersistenceEnabled]
  );

  const handleRenamePath = useCallback(
    (path: string) => {
      const parts = path.split('/');
      const currentName = parts.pop() || path;
      const parentPath = parts.join('/') || '/';
      const newName = window.prompt('Rename to', currentName);
      if (!newName || newName === currentName) return;

      const normalizedParent = parentPath === '/' ? '' : parentPath;
      const newPath = `${normalizedParent}/${newName}`;

      const isDirectory =
        extraDirectories.includes(path) || Object.keys(fileContents).some(p => p === path || p.startsWith(`${path}/`));

      if (isDirectory) {
        const updatedContents: Record<string, string> = {};
        Object.entries(fileContents).forEach(([filePath, content]) => {
          if (filePath === path || filePath.startsWith(`${path}/`)) {
            const updatedPath = filePath.replace(path, newPath);
            updatedContents[updatedPath] = content;
          } else {
            updatedContents[filePath] = content;
          }
        });

        savedContentsRef.current = Object.entries(savedContentsRef.current).reduce<Record<string, string>>(
          (acc, [filePath, content]) => {
            const updatedPath = filePath === path || filePath.startsWith(`${path}/`) ? filePath.replace(path, newPath) : filePath;
            acc[updatedPath] = content;
            return acc;
          },
          {}
        );

        const updatedDirs = extraDirectories.map(dir => (dir === path || dir.startsWith(`${path}/`) ? dir.replace(path, newPath) : dir));
        setExtraDirectories(updatedDirs);
        setFileContents(updatedContents);
        rebuildTreeFromContents(updatedContents, updatedDirs);
        setOpenTabs(prev => prev.map(tab => (tab === path || tab.startsWith(`${path}/`) ? tab.replace(path, newPath) : tab)));
        setSelectedFile(prev => (prev && (prev === path || prev.startsWith(`${path}/`)) ? prev.replace(path, newPath) : prev));
      } else {
        const updatedContents: Record<string, string> = {};
        Object.entries(fileContents).forEach(([filePath, content]) => {
          if (filePath === path) {
            updatedContents[newPath] = content;
          } else {
            updatedContents[filePath] = content;
          }
        });
        savedContentsRef.current = Object.entries(savedContentsRef.current).reduce<Record<string, string>>((acc, [filePath, content]) => {
          acc[filePath === path ? newPath : filePath] = content;
          return acc;
        }, {});
        setFileContents(updatedContents);
        rebuildTreeFromContents(updatedContents, extraDirectories);
        setOpenTabs(prev => prev.map(tab => (tab === path ? newPath : tab)));
        setSelectedFile(prev => (prev === path ? newPath : prev));
      }

      if (workspacePersistenceEnabled && authToken && workspaceId) {
        void renameWorkspacePath(authToken, workspaceId, path, newPath).catch(error => {
          console.error('Failed to rename path', error);
          setAutoSaveStatus('error');
          setAutoSaveError(getErrorMessage(error));
        });
      }
    },
    [authToken, extraDirectories, fileContents, getErrorMessage, rebuildTreeFromContents, workspaceId, workspacePersistenceEnabled]
  );

  const handleDeletePath = useCallback(
    (path: string) => {
      const isDirectory =
        extraDirectories.includes(path) || Object.keys(fileContents).some(p => p === path || p.startsWith(`${path}/`));
      const confirmMessage = isDirectory
        ? `Delete folder "${path}" and all nested files?`
        : `Delete file "${path}"?`;
      if (!window.confirm(confirmMessage)) return;

      const updatedContents: Record<string, string> = {};
      Object.entries(fileContents).forEach(([filePath, content]) => {
        if (filePath === path) return;
        if (isDirectory && filePath.startsWith(`${path}/`)) return;
        updatedContents[filePath] = content;
      });

      savedContentsRef.current = Object.entries(savedContentsRef.current).reduce<Record<string, string>>((acc, [filePath, content]) => {
        if (filePath === path) return acc;
        if (isDirectory && filePath.startsWith(`${path}/`)) return acc;
        acc[filePath] = content;
        return acc;
      }, {});

      const updatedDirs = extraDirectories.filter(dir => dir !== path && !(isDirectory && dir.startsWith(`${path}/`)));
      setExtraDirectories(updatedDirs);
      setFileContents(updatedContents);
      rebuildTreeFromContents(updatedContents, updatedDirs);
      setOpenTabs(prev => {
        const nextTabs = prev.filter(tab => !(tab === path || (isDirectory && tab.startsWith(`${path}/`))));
        setSelectedFile(prevSelected => {
          if (!prevSelected) return prevSelected;
          if (prevSelected === path || (isDirectory && prevSelected.startsWith(`${path}/`))) {
            return nextTabs[0] ?? null;
          }
          return prevSelected;
        });
        return nextTabs;
      });

      if (workspacePersistenceEnabled && authToken && workspaceId) {
        void deleteWorkspacePath(authToken, workspaceId, path, isDirectory).catch(error => {
          console.error('Failed to delete path', error);
          setAutoSaveStatus('error');
          setAutoSaveError(getErrorMessage(error));
        });
      }
    },
    [authToken, extraDirectories, fileContents, getErrorMessage, rebuildTreeFromContents, workspaceId, workspacePersistenceEnabled]
  );

  const handleGitStageAll = useCallback(async () => {
    if (!workspacePersistenceEnabled || !authToken || !workspaceId) return;
    setGitCommitOutput(null);
    try {
      await gitAdd(authToken, workspaceId);
      await refreshGitStatus();
    } catch (error) {
      console.error('Failed to stage files', error);
      setGitStatusError(getErrorMessage(error));
    }
  }, [authToken, getErrorMessage, refreshGitStatus, workspaceId, workspacePersistenceEnabled]);

  const handleGitCommit = useCallback(async () => {
    if (!workspacePersistenceEnabled || !authToken || !workspaceId) return;
    if (!gitCommitMessage.trim()) {
      setGitStatusError('Commit message required');
      return;
    }
    setGitCommitOutput(null);
    try {
      const result = await gitCommit(authToken, workspaceId, gitCommitMessage.trim());
      setGitCommitOutput(result.output || 'Committed');
      setGitCommitMessage('');
      await refreshGitStatus();
    } catch (error) {
      console.error('Failed to commit', error);
      setGitStatusError(getErrorMessage(error));
    }
  }, [authToken, getErrorMessage, gitCommitMessage, refreshGitStatus, workspaceId, workspacePersistenceEnabled]);

  const handleStartDebug = useCallback(async () => {
    if (!authToken || !sessionId) return;
    setDebugError(null);
    const trimmedArgs = debugArgs.trim();
    const args = trimmedArgs ? trimmedArgs.split(/\s+/) : [];
    const targetPath = debugTargetPath || selectedFile || '';
    try {
      const payload =
        debugLanguage === 'python'
          ? { language: 'python', file_path: targetPath, args }
          : {
              language: 'cpp',
              binary_path: targetPath,
              adapter: debugAdapter || undefined,
              args
            };
      const sessionInfo = await startDebugSession(authToken, sessionId, payload);
      setDebugSession(sessionInfo);
    } catch (error) {
      console.error('Failed to start debug session', error);
      setDebugError(getErrorMessage(error));
    }
  }, [authToken, debugAdapter, debugArgs, debugLanguage, debugTargetPath, getErrorMessage, selectedFile, sessionId]);

  const handleStopDebug = useCallback(async () => {
    if (!authToken || !sessionId || !debugSession) return;
    setDebugError(null);
    try {
      await stopDebugSession(authToken, sessionId, debugSession.debug_id);
      setDebugSession(null);
    } catch (error) {
      console.error('Failed to stop debug session', error);
      setDebugError(getErrorMessage(error));
    }
  }, [authToken, debugSession, getErrorMessage, sessionId]);

  const goToMarkerPosition = useCallback((line: number, column: number) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.revealPositionInCenter({ lineNumber: line, column });
    editor.setPosition({ lineNumber: line, column });
    editor.focus();
  }, []);

  const formatSeverity = useCallback((severity: monaco.MarkerSeverity) => {
    switch (severity) {
      case monaco.MarkerSeverity.Error:
        return 'Error';
      case monaco.MarkerSeverity.Warning:
        return 'Warning';
      case monaco.MarkerSeverity.Info:
        return 'Info';
      default:
        return 'Hint';
    }
  }, []);

  const startTerminalResize = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (isTerminalMinimized) return;

      const startY = e.clientY;
      const startHeight = terminalHeight;

      const handleMouseMove = (moveEvent: MouseEvent) => {
        const deltaY = startY - moveEvent.clientY;
        const newHeight = Math.max(160, Math.min(640, startHeight + deltaY));
        setTerminalHeight(newHeight);
      };

      const handleMouseUp = () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
        document.body.style.userSelect = '';
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = 'none';
    },
    [isTerminalMinimized, terminalHeight]
  );

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const uploadedFiles = event.target.files;
    if (!uploadedFiles || uploadedFiles.length === 0) return;

    const token = localStorage.getItem('token');
    const newFileDescriptors: WorkspaceFileDescriptor[] = [];
    let processedCount = 0;
    
    for (let i = 0; i < uploadedFiles.length; i++) {
      const file = uploadedFiles[i];
      const reader = new FileReader();
      
      reader.onload = async (e) => {
        const content = e.target?.result as string;
        const filePath = `/uploaded/${file.name}`;
        
        newFileDescriptors.push({
          path: filePath,
          content,
          language: inferLanguage(filePath)
        });
        
        processedCount++;

        // Rebuild file tree when all files are processed
        if (processedCount === uploadedFiles.length) {
          setTimeout(() => {
            // Get current file contents as descriptors
            const currentDescriptors: WorkspaceFileDescriptor[] = Object.entries(fileContents).map(([path, content]) => ({
              path,
              content,
              language: inferLanguage(path)
            }));
            
            // Merge and rebuild
            const allDescriptors = [...currentDescriptors, ...newFileDescriptors];
            const normalized = normalizedFiles(allDescriptors);
            
            // Update state
            const newContents: Record<string, string> = {};
            normalized.forEach(f => { newContents[f.path] = f.content; });
            
            setFileContents(newContents);
            setFiles(buildFileTree(normalized, extraDirectories));
          }, 100);
        }

        // Save to backend if persistence is enabled
        if (workspacePersistenceEnabled && token && workspaceId) {
          try {
            await upsertWorkspaceFile(token, workspaceId, {
              path: filePath,
              content,
              language: inferLanguage(filePath)
            });
          } catch (error) {
            console.error('Failed to save uploaded file:', error);
          }
        }
      };
      
      reader.readAsText(file);
    }
    
    // Reset input
    event.target.value = '';
  }, [workspaceId, workspacePersistenceEnabled, normalizedFiles, fileContents, extraDirectories]);

  const handleFolderUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const uploadedFiles = event.target.files;
    if (!uploadedFiles || uploadedFiles.length === 0) return;

    const token = localStorage.getItem('token');
    const newFileDescriptors: WorkspaceFileDescriptor[] = [];
    let processedCount = 0;

    // Process all files and extract their relative paths
    for (let i = 0; i < uploadedFiles.length; i++) {
      const file = uploadedFiles[i];
      // webkitRelativePath gives us the folder structure
      const relativePath = (file as any).webkitRelativePath || file.name;
      const filePath = `/${relativePath}`;
      
      const reader = new FileReader();
      
      reader.onload = async (e) => {
        const content = e.target?.result as string;
        
        newFileDescriptors.push({
          path: filePath,
          content,
          language: inferLanguage(filePath)
        });

        processedCount++;

        // Rebuild file tree when all files are processed
        if (processedCount === uploadedFiles.length) {
          setTimeout(() => {
            // Get current file contents as descriptors
            const currentDescriptors: WorkspaceFileDescriptor[] = Object.entries(fileContents).map(([path, content]) => ({
              path,
              content,
              language: inferLanguage(path)
            }));
            
            // Merge and rebuild
            const allDescriptors = [...currentDescriptors, ...newFileDescriptors];
            const normalized = normalizedFiles(allDescriptors);
            
            // Update state
            const newContents: Record<string, string> = {};
            normalized.forEach(f => { newContents[f.path] = f.content; });
            
            setFileContents(newContents);
            setFiles(buildFileTree(normalized, extraDirectories));
          }, 100);
        }

        // Save to backend if persistence is enabled
        if (workspacePersistenceEnabled && token && workspaceId) {
          try {
            await upsertWorkspaceFile(token, workspaceId, {
              path: filePath,
              content,
              language: inferLanguage(filePath)
            });
          } catch (error) {
            console.error('Failed to save folder file:', error);
          }
        }
      };
      
      reader.readAsText(file);
    }
    
    // Reset input
    event.target.value = '';
  }, [workspaceId, workspacePersistenceEnabled, normalizedFiles, fileContents, extraDirectories]);

  const autoSaveMessage = useMemo(() => {
    if (!workspacePersistenceEnabled) {
      return 'Autosave disabled for this workspace';
    }
    switch (autoSaveStatus) {
      case 'saving':
        return 'Saving…';
      case 'saved':
        return lastSavedAt ? `Saved ${lastSavedAt.toLocaleTimeString()}` : 'Saved';
      case 'error':
        return autoSaveError ? `Autosave failed: ${autoSaveError}` : 'Autosave failed';
      default:
        return 'Changes auto-save every few seconds';
    }
  }, [autoSaveStatus, autoSaveError, lastSavedAt, workspacePersistenceEnabled]);
  const autoSaveColor = useMemo(() => {
    switch (autoSaveStatus) {
      case 'error':
        return '#f87171';
      case 'saving':
        return '#38bdf8';
      case 'saved':
        return '#34d399';
      default:
        return '#a6a6a6';
    }
  }, [autoSaveStatus]);

  if (isLoadingFiles) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          backgroundColor: '#1e1e1e',
          color: '#d4d4d8',
          fontSize: '0.95rem'
        }}
      >
        Loading workspace files…
      </div>
    );
  }

  const shellStyle: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    backgroundColor: '#1f1f1f',
    color: '#d4d4d8',
    fontFamily: '"Segoe UI", "SFMono-Regular", system-ui, sans-serif'
  };

  const activityBarStyle: CSSProperties = {
    width: 54,
    backgroundColor: '#202123',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '0.65rem 0.5rem',
    gap: '0.45rem',
    borderRight: '1px solid #1b1b1d'
  };

  const sideBarStyle: CSSProperties = {
    width: 260,
    backgroundColor: '#252526',
    borderRight: '1px solid #1b1b1d',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    color: '#d4d4d8'
  };

  const sectionHeaderStyle: CSSProperties = {
    padding: '0.65rem 1rem',
    fontSize: '0.72rem',
    letterSpacing: '0.12em',
    fontWeight: 600,
    color: '#9da5b4',
    textTransform: 'uppercase'
  };

  const openEditorItemStyle = (active: boolean): CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: '0.45rem',
    padding: '0.35rem 1rem',
    cursor: 'pointer',
    backgroundColor: active ? '#37373d' : 'transparent',
    color: active ? '#f3f4f6' : '#d4d4d8',
    borderLeft: active ? '2px solid #007acc' : '2px solid transparent',
    fontSize: '0.85rem'
  });

  const sideActionButtonStyle: CSSProperties = {
    width: 32,
    height: 32,
    borderRadius: '6px',
    border: '1px solid #2f2f2f',
    background: '#2a2d2e',
    color: '#cbd5f5',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer'
  };

  const panelButtonStyle: CSSProperties = {
    width: 26,
    height: 26,
    borderRadius: '4px',
    border: '1px solid #2f2f2f',
    background: '#2a2d2e',
    color: '#cbd5f5',
    fontSize: '0.75rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer'
  };

  const panelTabStyle = (active: boolean): CSSProperties => ({
    height: 24,
    padding: '0 0.75rem',
    borderRadius: '4px',
    border: 'none',
    fontSize: '0.75rem',
    textTransform: 'uppercase',
    cursor: 'pointer',
    backgroundColor: active ? '#1e1e1e' : 'transparent',
    color: active ? '#f3f4f6' : '#9da5b4'
  });

  const statusBarStyle: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#007acc',
    color: '#f3f4f6',
    padding: '0 1rem',
    height: 24,
    fontSize: '0.75rem'
  };

  return (
    <>
      <style>{gitDecorationStyles}</style>
      <div style={shellStyle}>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <aside style={activityBarStyle}>
          {activityItems.map(item => {
            const isActive = activeActivity === item.label;
            return (
              <button
                key={item.label}
                title={item.label}
                style={{
                  ...activityButtonStyle,
                  background: isActive ? '#3b3d42' : 'transparent',
                  color: isActive ? '#f3f4f6' : '#9ca3af',
                  borderLeft: isActive ? '2px solid #007acc' : '2px solid transparent'
                }}
                onClick={() => setActiveActivity(item.label)}
              >
                <span aria-hidden="true">{item.icon}</span>
              </button>
            );
          })}
          <div
            style={{
              marginTop: 'auto',
              fontSize: '0.7rem',
              color: '#6b7280',
              writingMode: 'vertical-rl',
              transform: 'rotate(180deg)',
              letterSpacing: '0.25em'
            }}
          >
            CO·SIM
          </div>
        </aside>

        <aside style={sideBarStyle}>
          <div style={sectionHeaderStyle}>Explorer</div>
          {activeActivity === 'Explorer' ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 1rem 0.75rem', gap: '0.5rem' }}>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  style={sideActionButtonStyle}
                  title="Upload file(s)"
                >
                  <Upload size={16} />
                </button>
                <button
                  onClick={() => folderInputRef.current?.click()}
                  style={sideActionButtonStyle}
                  title="Upload folder"
                >
                  <FolderUp size={16} />
                </button>
              </div>

              <div style={{ borderTop: '1px solid #2f2f2f', borderBottom: '1px solid #2f2f2f' }}>
                <div style={sectionHeaderStyle}>Open Editors</div>
                <div>
                  {openTabs.length === 0 ? (
                    <div style={{ padding: '0.35rem 1rem', fontSize: '0.75rem', color: '#7c8187' }}>
                      No editors open
                    </div>
                  ) : (
                    openTabs.map(path => {
                      const isActive = selectedFile === path;
                      const isDirtyTab = dirtyTabs.has(path);
                      const name = path.split('/').pop() ?? path;
                      return (
                        <div
                          key={`open-${path}`}
                          onClick={() => handleTabSelect(path)}
                          style={openEditorItemStyle(isActive)}
                        >
                          <span
                            style={{
                              flex: 1,
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              textAlign: 'left'
                            }}
                          >
                            {name}
                          </span>
                          {isDirtyTab && <span style={{ color: '#facc15', fontSize: '0.7rem' }}>●</span>}
                          <button
                            onClick={(event) => handleTabClose(path, event)}
                            style={{
                              border: 'none',
                              background: 'transparent',
                              color: '#9ca3af',
                              cursor: 'pointer',
                              fontSize: '0.75rem'
                            }}
                          >
                            ×
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
              <input
                ref={folderInputRef}
                type="file"
                {...({ webkitdirectory: '', directory: '' } as any)}
                onChange={handleFolderUpload}
                style={{ display: 'none' }}
              />

              <div style={{ flex: 1, overflowY: 'auto', padding: '0.35rem 0.5rem 1rem' }}>
                <FileTree
                  files={files}
                  selectedFile={selectedFile}
                  onFileSelect={handleFileSelect}
                  onCreateFile={handleCreatePath}
                  onRenamePath={handleRenamePath}
                  onDeletePath={handleDeletePath}
                />
              </div>
            </>
          ) : activeActivity === 'Source Control' ? (
            <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ fontWeight: 600, color: '#e5e7eb' }}>Source Control</div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button
                  onClick={() => void refreshGitStatus()}
                  style={toolbarButtonBase}
                  disabled={!authToken || !workspacePersistenceEnabled}
                >
                  Refresh
                </button>
                <button
                  onClick={() => void handleGitStageAll()}
                  style={toolbarButtonBase}
                  disabled={!authToken || !workspacePersistenceEnabled}
                >
                  Stage All
                </button>
              </div>
              {!workspacePersistenceEnabled || !authToken ? (
                <div style={{ color: '#9ca3af', fontSize: '0.9rem' }}>
                  Git status is available once you are signed in and using a persisted workspace.
                </div>
              ) : (
                <>
              {gitStatusError && (
                <div style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{gitStatusError}</div>
              )}
              {isGitLoading ? (
                <div style={{ color: '#9ca3af', fontSize: '0.9rem' }}>Loading git status…</div>
              ) : gitStatus.length === 0 ? (
                <div style={{ color: '#9ca3af', fontSize: '0.9rem' }}>No changes detected.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', fontSize: '0.85rem' }}>
                  {gitStatus.map(entry => (
                    <div key={entry.path} style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem' }}>
                      <span style={{ color: '#9ca3af', fontFamily: 'SFMono-Regular, monospace' }}>
                        {entry.staged}{entry.unstaged}
                      </span>
                      <span style={{ flex: 1, color: '#e5e7eb' }}>{entry.path}</span>
                    </div>
                  ))}
                </div>
              )}
              <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                <input
                  value={gitCommitMessage}
                  onChange={event => setGitCommitMessage(event.target.value)}
                  placeholder="Commit message"
                  style={{
                    flex: 1,
                    background: '#1f1f1f',
                    border: '1px solid #333',
                    borderRadius: 6,
                    color: '#e5e7eb',
                    padding: '0.45rem 0.6rem',
                    fontSize: '0.85rem'
                  }}
                />
                <button
                  onClick={() => void handleGitCommit()}
                  style={toolbarButtonBase}
                  disabled={!authToken || !workspacePersistenceEnabled}
                >
                  Commit
                </button>
              </div>
              {gitCommitOutput && (
                <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>{gitCommitOutput}</div>
              )}
                </>
              )}
            </div>
          ) : activeActivity === 'Debug' ? (
            <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ fontWeight: 600, color: '#e5e7eb' }}>Debug</div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <select
                  value={debugLanguage}
                  onChange={event => setDebugLanguage(event.target.value as 'python' | 'cpp')}
                  style={{
                    background: '#1f1f1f',
                    border: '1px solid #333',
                    borderRadius: 6,
                    color: '#e5e7eb',
                    padding: '0.4rem 0.5rem',
                    fontSize: '0.85rem'
                  }}
                >
                  <option value="python">Python (debugpy)</option>
                  <option value="cpp">C++ (gdb/lldb)</option>
                </select>
                {debugLanguage === 'cpp' && (
                  <select
                    value={debugAdapter}
                    onChange={event => setDebugAdapter(event.target.value as 'gdb' | 'lldb' | '')}
                    style={{
                      background: '#1f1f1f',
                      border: '1px solid #333',
                      borderRadius: 6,
                      color: '#e5e7eb',
                      padding: '0.4rem 0.5rem',
                      fontSize: '0.85rem'
                    }}
                  >
                    <option value="">Auto</option>
                    <option value="gdb">gdb</option>
                    <option value="lldb">lldb</option>
                  </select>
                )}
              </div>
              <input
                value={debugTargetPath}
                onChange={event => setDebugTargetPath(event.target.value)}
                placeholder={debugLanguage === 'python' ? 'Script path (e.g. /src/main.py)' : 'Binary path (e.g. /build/app)'}
                style={{
                  background: '#1f1f1f',
                  border: '1px solid #333',
                  borderRadius: 6,
                  color: '#e5e7eb',
                  padding: '0.45rem 0.6rem',
                  fontSize: '0.85rem'
                }}
              />
              <input
                value={debugArgs}
                onChange={event => setDebugArgs(event.target.value)}
                placeholder="Arguments (optional)"
                style={{
                  background: '#1f1f1f',
                  border: '1px solid #333',
                  borderRadius: 6,
                  color: '#e5e7eb',
                  padding: '0.45rem 0.6rem',
                  fontSize: '0.85rem'
                }}
              />
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button onClick={() => void handleStartDebug()} style={toolbarButtonBase} disabled={!authToken}>
                  Start Debug
                </button>
                <button
                  onClick={() => void handleStopDebug()}
                  style={toolbarButtonBase}
                  disabled={!authToken || !debugSession}
                >
                  Stop
                </button>
              </div>
              {debugError && <div style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{debugError}</div>}
              {debugSession && (
                <div style={{ fontSize: '0.85rem', color: '#9ca3af', lineHeight: 1.5 }}>
                  <div>Debug session ready.</div>
                  <div>Port: <span style={{ color: '#e5e7eb' }}>{debugSession.port}</span></div>
                  <div>Command: <span style={{ color: '#e5e7eb' }}>{debugSession.command.join(' ')}</span></div>
                  <div>Working dir: <span style={{ color: '#e5e7eb' }}>{debugSession.working_dir}</span></div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: '1rem', fontSize: '0.85rem', color: '#9da5b4' }}>
              {activeActivity} view coming soon.
            </div>
          )}
        </aside>

        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', backgroundColor: '#1e1e1e' }}>
          <div style={{ display: 'flex', alignItems: 'center', borderBottom: '1px solid #1f1f1f', backgroundColor: '#2d2d2d' }}>
            <div style={{ display: 'flex', alignItems: 'stretch', flex: 1, overflowX: 'auto' }}>
              {openTabs.length === 0 ? (
                <div style={{ padding: '0.5rem 1rem', color: '#9ca3af', fontSize: '0.8rem' }}>No file open</div>
              ) : (
                openTabs.map(path => {
                  const name = path.split('/').pop() ?? path;
                  const isActive = selectedFile === path;
                  const isDirtyTab = dirtyTabs.has(path);
                  return (
                    <div
                      key={`tab-${path}`}
                      style={tabStyle(isActive)}
                      onClick={() => handleTabSelect(path)}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{name}</span>
                      {isDirtyTab && <span style={{ color: '#facc15', fontSize: '0.65rem' }}>●</span>}
                      <button
                        onClick={(event) => handleTabClose(path, event)}
                        style={{ ...tabCloseButtonStyle, color: isActive ? '#f3f4f6' : '#9ca3af' }}
                        title="Close"
                      >
                        ×
                      </button>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0.6rem 1rem',
              backgroundColor: '#1e1e1e',
              borderBottom: '1px solid #1f1f1f',
              gap: '1rem',
              flexWrap: 'wrap'
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f3f4f6', fontWeight: 600 }}>
                {currentFile?.name ?? 'Select a file'}
                {isDirty && <span style={{ color: '#facc15', fontSize: '0.75rem' }}>●</span>}
                {currentLanguage && (
                  <span
                    style={{
                      fontSize: '0.7rem',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                      background: 'rgba(148, 163, 184, 0.15)',
                      borderRadius: '999px',
                      padding: '0.1rem 0.45rem',
                      color: '#94a3b8'
                    }}
                  >
                    {currentLanguage}
                  </span>
                )}
              </div>
              <div style={{ color: '#9ca3af', fontSize: '0.78rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {breadcrumbs.length > 0 ? breadcrumbs.join(' / ') : 'workspace'}
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end', flex: '1 1 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', flexWrap: 'wrap' }}>
                <button
                  style={{
                    ...toolbarButtonBase,
                    opacity: selectedFile ? 1 : 0.5,
                    cursor: selectedFile ? 'pointer' : 'not-allowed'
                  }}
                  onClick={() => void handleSave()}
                  disabled={!selectedFile}
                  title="Save (Ctrl/Cmd + S)"
                >
                  💾 Save
                </button>
                <button
                  style={{
                    ...toolbarButtonBase,
                    opacity: selectedFile && currentLanguage !== 'text' ? 1 : 0.5,
                    cursor: selectedFile && currentLanguage !== 'text' ? 'pointer' : 'not-allowed'
                  }}
                  onClick={handleFormatDocument}
                  disabled={!selectedFile || currentLanguage === 'text'}
                  title="Format document"
                >
                  ✨ Format
                </button>
                <button
                  style={{
                    ...toolbarButtonBase,
                    background: showMinimap ? 'rgba(0, 122, 204, 0.18)' : 'transparent',
                    borderColor: showMinimap ? '#007acc' : '#3e3e42',
                    color: showMinimap ? '#e5f2ff' : '#d0d0d0'
                  }}
                  onClick={handleMinimapToggle}
                  title="Toggle minimap"
                >
                  🗺️ Minimap
                </button>
                <button
                  style={{
                    ...toolbarButtonBase,
                    background: isDarkTheme ? 'linear-gradient(135deg, rgba(76, 106, 219, 0.35), rgba(129, 140, 248, 0.35))' : 'rgba(15, 23, 42, 0.1)',
                    borderColor: isDarkTheme ? 'rgba(129, 140, 248, 0.65)' : '#cbd5f5',
                    color: isDarkTheme ? '#f8fafc' : '#0f172a'
                  }}
                  onClick={handleThemeToggle}
                  title="Toggle theme"
                >
                  {isDarkTheme ? '🌙 Dark' : '🌞 Light'}
                </button>
                {selectedFile?.endsWith('.py') && (
                  <button
                    style={{
                      ...toolbarButtonBase,
                      background: isExecuting ? 'rgba(148, 163, 184, 0.25)' : 'linear-gradient(135deg, #0dbc79 0%, #23d18b 100%)',
                      borderColor: '#0b6e4f',
                      color: '#032d26',
                      cursor: isExecuting ? 'not-allowed' : 'pointer'
                    }}
                    onClick={handleRunPython}
                    disabled={isExecuting}
                    title="Run Python"
                  >
                    {isExecuting ? '⏳ Running…' : '▶️ Run'}
                  </button>
                )}
                {selectedFile?.endsWith('.cpp') && (
                  <>
                    <button
                      style={{
                        ...toolbarButtonBase,
                        background: isBuilding ? 'rgba(148, 163, 184, 0.25)' : 'linear-gradient(135deg, #facc15 0%, #f97316 100%)',
                        borderColor: 'rgba(234, 179, 8, 0.6)',
                        color: '#1f2937',
                        cursor: isBuilding ? 'not-allowed' : 'pointer'
                      }}
                      onClick={handleBuildCpp}
                      disabled={isBuilding}
                      title="Build C++"
                    >
                      {isBuilding ? '⏳ Building…' : '🔨 Build'}
                    </button>
                    {lastBinary && (
                      <button
                        style={{
                          ...toolbarButtonBase,
                          background: isExecuting ? 'rgba(148, 163, 184, 0.25)' : 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                          borderColor: 'rgba(37, 99, 235, 0.6)',
                          color: '#f8fafc',
                          cursor: isExecuting ? 'not-allowed' : 'pointer'
                        }}
                        onClick={handleRunBinary}
                        disabled={isExecuting}
                        title="Run latest binary"
                      >
                        {isExecuting ? '⏳ Running…' : '▶️ Run'}
                      </button>
                    )}
                    <button
                      style={{
                        ...toolbarButtonBase,
                        background: isBuilding || isExecuting ? 'rgba(148, 163, 184, 0.25)' : 'linear-gradient(135deg, #ec4899 0%, #d946ef 100%)',
                        borderColor: 'rgba(190, 24, 93, 0.6)',
                        color: '#f8fafc',
                        cursor: isBuilding || isExecuting ? 'not-allowed' : 'pointer'
                      }}
                      onClick={handleBuildAndRun}
                      disabled={isBuilding || isExecuting}
                      title="Build and run"
                    >
                      {isBuilding || isExecuting ? '⏳ Processing…' : '⚡ Build & Run'}
                    </button>
                  </>
                )}
              </div>
              <div style={{ display: 'flex', gap: '0.35rem' }}>
                {(['editor-only', 'with-terminal'] as const).map(mode => (
                  <button
                    key={mode}
                    onClick={() => setLayout(mode)}
                    style={layoutButtonStyle(layout === mode)}
                  >
                    {mode === 'editor-only' ? 'Editor' : 'Editor + Terminal'}
                  </button>
                ))}
              </div>
              <span style={{ color: autoSaveColor, fontSize: '0.75rem' }}>{autoSaveMessage}</span>
            </div>
          </div>

          {loadError && (
            <div
              style={{
                backgroundColor: '#3e3e42',
                color: '#fbbf24',
                padding: '0.5rem 1rem',
                fontSize: '0.8rem',
                borderBottom: '1px solid #1f1f1f'
              }}
            >
              {loadError}
            </div>
          )}

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ flex: 1, minHeight: 0 }}>
              <Editor
                language={currentLanguage}
                theme={editorTheme}
                value={currentContent}
                onChange={handleChange}
                onMount={handleEditorMount}
                path={selectedFile || undefined}
                options={{
                  minimap: {
                    enabled: showMinimap,
                    maxColumn: 120,
                    renderCharacters: false,
                    showSlider: 'mouseover',
                    size: 'proportional'
                  },
                  fontSize: 14,
                  lineHeight: 22,
                  fontLigatures: true,
                  letterSpacing: 0,
                  renderLineHighlight: 'all',
                  renderLineHighlightOnlyWhenFocus: true,
                  renderWhitespace: 'selection',
                  renderControlCharacters: true,
                  guides: {
                    indentation: true,
                    bracketPairs: true,
                    bracketPairsHorizontal: true,
                    highlightActiveIndentation: true
                  },
                  bracketPairColorization: { enabled: true },
                  folding: true,
                  foldingHighlight: true,
                  stickyScroll: { enabled: true },
                  rulers: [80, 120],
                  overviewRulerBorder: false,
                  automaticLayout: true,
                  smoothScrolling: true,
                  scrollBeyondLastLine: false,
                  wordWrap: 'on',
                  tabSize: 4,
                  insertSpaces: true,
                  lineNumbersMinChars: 3,
                  lineDecorationsWidth: 14,
                  padding: { top: 4, bottom: 4 },
                  cursorBlinking: 'blink',
                  cursorSmoothCaretAnimation: 'on',
                  scrollbar: {
                    verticalScrollbarSize: 10,
                    horizontalScrollbarSize: 10,
                    alwaysConsumeMouseWheel: false
                  },
                  glyphMargin: true
                }}
                loading={
                  <div style={{ color: '#a1a1aa', fontSize: '0.9rem', padding: '1rem' }}>
                    Loading editor…
                  </div>
                }
              />
            </div>

            {layout === 'with-terminal' && (
              <div
                style={{
                  borderTop: '1px solid #1f1f1f',
                  backgroundColor: '#1e1e1e',
                  display: 'flex',
                  flexDirection: 'column',
                  height: isTerminalMinimized ? 40 : terminalHeight,
                  minHeight: 40,
                  transition: 'height 0.2s ease'
                }}
              >
                <div
                  style={{
                    height: 38,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '0 0.75rem',
                    backgroundColor: '#252526',
                    borderBottom: isTerminalMinimized ? 'none' : '1px solid #1f1f1f'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    {PANEL_TABS.map(tab => {
                      const isActive = activePanelTab === tab;
                      return (
                        <button
                          key={tab}
                          style={panelTabStyle(isActive)}
                          onClick={() => setActivePanelTab(tab)}
                        >
                          {tab.toUpperCase()}
                        </button>
                      );
                    })}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <button
                      onClick={() => setIsTerminalMinimized(!isTerminalMinimized)}
                      style={panelButtonStyle}
                      title={isTerminalMinimized ? 'Restore panel' : 'Collapse panel'}
                    >
                      {isTerminalMinimized ? '▢' : '⌄'}
                    </button>
                    <button
                      onClick={() => setTerminalHeight(Math.min(640, terminalHeight + 60))}
                      style={panelButtonStyle}
                      title="Increase height"
                    >
                      ＋
                    </button>
                    <button
                      onClick={() => setTerminalHeight(Math.max(180, terminalHeight - 60))}
                      style={panelButtonStyle}
                      title="Decrease height"
                    >
                      －
                    </button>
                  </div>
                </div>

                {!isTerminalMinimized && (
                  <div style={{ flex: 1, display: 'flex', backgroundColor: '#1e1e1e' }}>
                    {activePanelTab === 'Terminal' && (
                      <Terminal
                        sessionId={sessionId}
                        token={localStorage.getItem('token') || undefined}
                        onCommand={handleTerminalCommand}
                        height="100%"
                        executionOutput={executionOutput}
                      />
                    )}
                    {activePanelTab === 'Output' && (
                      <div style={{ flex: 1, padding: '0.75rem', fontFamily: 'SFMono-Regular, Menlo, monospace', color: '#e5e7eb', overflow: 'auto' }}>
                        {executionOutput?.stdout && (
                          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#d1fae5' }}>{executionOutput.stdout}</pre>
                        )}
                        {executionOutput?.stderr && (
                          <pre style={{ marginTop: '0.75rem', whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: '#fecdd3' }}>{executionOutput.stderr}</pre>
                        )}
                        {!executionOutput?.stdout && !executionOutput?.stderr && (
                          <div style={{ color: '#9ca3af', fontSize: '0.9rem' }}>No output yet. Run a task to see logs.</div>
                        )}
                      </div>
                    )}
                    {activePanelTab === 'Debug Console' && (
                      <div style={{ flex: 1, padding: '0.75rem', color: '#9ca3af', fontSize: '0.9rem' }}>
                        {debugSession ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                            <div style={{ color: '#e5e7eb' }}>Debug session active</div>
                            <div>Attach using host <span style={{ color: '#e5e7eb' }}>localhost</span> and port <span style={{ color: '#e5e7eb' }}>{debugSession.port}</span>.</div>
                            <div>Command: <span style={{ color: '#e5e7eb' }}>{debugSession.command.join(' ')}</span></div>
                          </div>
                        ) : (
                          <div>Start a debug session to see connection details.</div>
                        )}
                      </div>
                    )}
                    {activePanelTab === 'Problems' && (
                      <div style={{ flex: 1, overflow: 'auto', background: '#1b1d1f' }}>
                        {problems.length === 0 ? (
                          <div style={{ padding: '0.75rem', color: '#9ca3af' }}>No problems detected.</div>
                        ) : (
                          problems.map((problem, idx) => (
                            <button
                              key={`${problem.message}-${idx}`}
                              onClick={() => goToMarkerPosition(problem.line, problem.column)}
                              style={{
                                width: '100%',
                                textAlign: 'left',
                                padding: '0.65rem 0.85rem',
                                background: 'transparent',
                                border: 'none',
                                color: '#e5e7eb',
                                borderBottom: '1px solid #2a2a2a',
                                display: 'flex',
                                justifyContent: 'space-between',
                                gap: '0.5rem',
                                cursor: 'pointer'
                              }}
                            >
                              <span style={{ display: 'flex', gap: '0.5rem' }}>
                                <span
                                  style={{
                                    fontWeight: 700,
                                    color:
                                      problem.severity === monaco.MarkerSeverity.Error
                                        ? '#fca5a5'
                                        : problem.severity === monaco.MarkerSeverity.Warning
                                          ? '#facc15'
                                          : '#93c5fd'
                                  }}
                                >
                                  {formatSeverity(problem.severity)}
                                </span>
                                <span style={{ color: '#d1d5db' }}>{problem.message}</span>
                              </span>
                              <span style={{ color: '#9ca3af', fontSize: '0.85rem' }}>
                                {problem.line}:{problem.column}
                              </span>
                            </button>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                )}

                {!isTerminalMinimized && (
                  <div
                    style={{
                      height: '6px',
                      cursor: 'ns-resize',
                      background: 'linear-gradient(90deg, rgba(0, 122, 204, 0.35), rgba(0, 122, 204, 0.05))'
                    }}
                    onMouseDown={startTerminalResize}
                  />
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {showCommandPalette && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.45)',
            zIndex: 20,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'center',
            paddingTop: '10vh'
          }}
          onClick={() => setShowCommandPalette(false)}
        >
          <div
            style={{
              width: '520px',
              background: '#1e1e1e',
              border: '1px solid #2f2f2f',
              borderRadius: 8,
              boxShadow: '0 10px 50px rgba(0,0,0,0.35)',
              overflow: 'hidden'
            }}
            onClick={e => e.stopPropagation()}
          >
            <input
              autoFocus
              value={commandFilter}
              onChange={e => setCommandFilter(e.target.value)}
              placeholder="Type a command (e.g. theme, minimap, format)…"
              style={{
                width: '100%',
                padding: '12px 14px',
                background: '#252526',
                border: 'none',
                color: '#f3f4f6',
                fontSize: '0.95rem',
                outline: 'none'
              }}
            />
            <div style={{ maxHeight: 320, overflowY: 'auto' }}>
              {filteredCommands.length === 0 ? (
                <div style={{ padding: '12px 14px', color: '#9ca3af', fontSize: '0.9rem' }}>No commands found</div>
              ) : (
                filteredCommands.map((cmd, idx) => {
                  const active = idx === commandSelection;
                  return (
                    <button
                      key={cmd.id}
                      onClick={() => executeCommand(cmd.id)}
                      onMouseEnter={() => setCommandSelection(idx)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: '10px 14px',
                        background: active ? '#094771' : 'transparent',
                        border: 'none',
                        borderBottom: '1px solid #2a2a2a',
                        color: '#e5e7eb',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}
                    >
                      <span>{cmd.label}</span>
                      <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>{cmd.detail}</span>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        </div>
      )}

      <footer style={statusBarStyle}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          {statusLeft.map((item, index) => (
            <span key={`${item}-${index}`}>{item}</span>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {statusRight.map((item, index) => (
            <span key={`${item}-${index}`}>{item}</span>
          ))}
        </div>
      </footer>
    </div>
    </>
  );
};

export default SessionIDE;
