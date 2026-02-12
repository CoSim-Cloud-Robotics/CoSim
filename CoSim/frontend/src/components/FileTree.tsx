import { ChevronDown, ChevronRight, File, Folder, FolderOpen } from 'lucide-react';
import { useState } from 'react';

export interface FileNode {
  id: string;
  name: string;
  type: 'file' | 'directory';
  path: string;
  children?: FileNode[];
  language?: 'python' | 'cpp' | 'text';
}

interface FileTreeProps {
  files: FileNode[];
  selectedFile: string | null;
  onFileSelect: (file: FileNode) => void;
  onCreateFile?: (parentPath: string, name: string, type: 'file' | 'directory') => void;
  onRenamePath?: (path: string) => void;
  onDeletePath?: (path: string) => void;
}

export const FileTree = ({ files, selectedFile, onFileSelect, onCreateFile, onRenamePath, onDeletePath }: FileTreeProps) => {
  const [contextTarget, setContextTarget] = useState<{ x: number; y: number; node: FileNode } | null>(null);

  const closeContext = () => setContextTarget(null);

  const handleContextAction = (action: 'new-file' | 'new-folder' | 'rename' | 'delete') => {
    if (!contextTarget) return;
    const { node } = contextTarget;
    const parentPath = node.type === 'directory' ? node.path : node.path.split('/').slice(0, -1).join('/') || '/';
    switch (action) {
      case 'new-file':
        if (onCreateFile) onCreateFile(parentPath, 'untitled', 'file');
        break;
      case 'new-folder':
        if (onCreateFile) onCreateFile(parentPath, 'new-folder', 'directory');
        break;
      case 'rename':
        if (onRenamePath) onRenamePath(node.path);
        break;
      case 'delete':
        if (onDeletePath) onDeletePath(node.path);
        break;
    }
    closeContext();
  };

  return (
    <div className="file-tree" style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem', position: 'relative' }}>
      {files.map(node => (
        <TreeNode
          key={node.id}
          node={node}
          level={0}
          selectedFile={selectedFile}
          onFileSelect={onFileSelect}
          onCreateFile={onCreateFile}
          onRenamePath={onRenamePath}
          onDeletePath={onDeletePath}
          onContextMenu={setContextTarget}
        />
      ))}
      {contextTarget && (
        <div
          style={{
            position: 'absolute',
            top: contextTarget.y,
            left: contextTarget.x,
            background: '#252526',
            border: '1px solid #3c3c3c',
            borderRadius: 4,
            boxShadow: '0 6px 24px rgba(0,0,0,0.35)',
            minWidth: 180,
            zIndex: 5
          }}
          onMouseLeave={closeContext}
        >
          {onCreateFile && (
            <>
              <ContextMenuItem label="New File" onClick={() => handleContextAction('new-file')} />
              <ContextMenuItem label="New Folder" onClick={() => handleContextAction('new-folder')} />
            </>
          )}
          {onRenamePath && <ContextMenuItem label="Rename" onClick={() => handleContextAction('rename')} />}
          {onDeletePath && <ContextMenuItem label="Delete" onClick={() => handleContextAction('delete')} />}
        </div>
      )}
    </div>
  );
};

interface TreeNodeProps {
  node: FileNode;
  level: number;
  selectedFile: string | null;
  onFileSelect: (file: FileNode) => void;
  onCreateFile?: (parentPath: string, name: string, type: 'file' | 'directory') => void;
  onRenamePath?: (path: string) => void;
  onDeletePath?: (path: string) => void;
  onContextMenu?: (target: { x: number; y: number; node: FileNode }) => void;
}

const TreeNode = ({ node, level, selectedFile, onFileSelect, onCreateFile, onRenamePath, onDeletePath, onContextMenu }: TreeNodeProps) => {
  const [isExpanded, setIsExpanded] = useState(level === 0);
  const [isHovered, setIsHovered] = useState(false);
  const isSelected = node.path === selectedFile;
  const hasChildren = node.children && node.children.length > 0;

  const handleClick = () => {
    if (node.type === 'directory') {
      setIsExpanded(!isExpanded);
    } else {
      onFileSelect(node);
    }
  };

  const getFileIcon = () => {
    if (node.type === 'directory') {
      return isExpanded ? <FolderOpen size={16} /> : <Folder size={16} />;
    }
    return <File size={16} />;
  };

  const getFileColor = () => {
    if (node.type === 'directory') return '#90caf9';
    if (node.language === 'python') return '#ffd166';
    if (node.language === 'cpp') return '#6ee7b7';
    return '#a6accd';
  };

  const backgroundColor = isSelected ? '#37373d' : isHovered ? 'rgba(42, 45, 46, 0.75)' : 'transparent';
  const textColor = isSelected ? '#f3f4f6' : '#d4d4d8';

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleClick();
    }
    if (event.key === 'ArrowRight') {
      if (node.type === 'directory' && !isExpanded) {
        event.preventDefault();
        setIsExpanded(true);
      } else if (node.type === 'file') {
        onFileSelect(node);
      }
    }
    if (event.key === 'ArrowLeft' && node.type === 'directory' && isExpanded) {
      event.preventDefault();
      setIsExpanded(false);
    }
    if (event.key === 'F2' && onRenamePath) {
      event.preventDefault();
      onRenamePath(node.path);
    }
    if ((event.key === 'Delete' || event.key === 'Backspace') && onDeletePath) {
      event.preventDefault();
      onDeletePath(node.path);
    }
  };

  return (
    <div>
      <div
        onClick={handleClick}
        className={`tree-node ${isSelected ? 'selected' : ''}`}
        style={{
          paddingLeft: `${level * 14 + 10}px`,
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          padding: '0.32rem 0.5rem',
          cursor: 'pointer',
          userSelect: 'none',
          backgroundColor,
          borderLeft: isSelected ? '2px solid #007acc' : '2px solid transparent',
          transition: 'background-color 0.15s ease'
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onContextMenu={e => {
          e.preventDefault();
          onContextMenu?.({ x: e.clientX, y: e.clientY, node });
        }}
        tabIndex={0}
        role="treeitem"
        aria-selected={isSelected}
        onKeyDown={handleKeyDown}
      >
        {node.type === 'directory' && (
          <span style={{ display: 'flex', alignItems: 'center', color: '#9da5b4' }}>
            {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        )}
        {node.type === 'file' && <span style={{ width: '14px' }} />}
        <span style={{ color: getFileColor(), display: 'flex', alignItems: 'center' }}>
          {getFileIcon()}
        </span>
        <span
          style={{
            fontSize: '0.85rem',
            color: textColor,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}
        >
          {node.name}
        </span>
      </div>
      {node.type === 'directory' && isExpanded && hasChildren && (
        <div>
          {node.children!.map(child => (
            <TreeNode
              key={child.id}
              node={child}
              level={level + 1}
              selectedFile={selectedFile}
              onFileSelect={onFileSelect}
              onCreateFile={onCreateFile}
              onRenamePath={onRenamePath}
              onDeletePath={onDeletePath}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default FileTree;

const ContextMenuItem = ({ label, onClick }: { label: string; onClick: () => void }) => (
  <button
    onClick={onClick}
    style={{
      width: '100%',
      textAlign: 'left',
      padding: '8px 12px',
      background: 'transparent',
      border: 'none',
      color: '#f3f4f6',
      cursor: 'pointer',
      borderBottom: '1px solid #313131'
    }}
  >
    {label}
  </button>
);
