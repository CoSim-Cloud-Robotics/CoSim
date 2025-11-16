import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { fetchProjects } from '../api/projects';
import { fetchOrganizations, createOrganization } from '../api/organizations';
import type { Project, Organization } from '../api/types';
import Layout from '../components/Layout';
import { useAuth } from '../hooks/useAuth';
import { authorizedClient } from '../api/client';

// Icons (simple SVG components)
const PlusIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="12" y1="5" x2="12" y2="19"></line>
    <line x1="5" y1="12" x2="19" y2="12"></line>
  </svg>
);

const CodeIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <polyline points="16 18 22 12 16 6"></polyline>
    <polyline points="8 6 2 12 8 18"></polyline>
  </svg>
);

const RobotIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <rect x="6" y="10" width="12" height="10" rx="2"></rect>
    <path d="M12 10V6"></path>
    <circle cx="12" cy="4" r="2"></circle>
    <circle cx="9" cy="14" r="1"></circle>
    <circle cx="15" cy="14" r="1"></circle>
  </svg>
);

const FolderIcon = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
  </svg>
);

const CloseIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <line x1="18" y1="6" x2="6" y2="18"></line>
    <line x1="6" y1="6" x2="18" y2="18"></line>
  </svg>
);

interface CreateProjectPayload {
  name: string;
  description?: string;
  organization_id: string;
  slug: string;
  template_id?: string;
  selectedTemplate?: string | null;  // For determining engine
}

const TEMPLATES = [
  {
    id: 'rl-mujoco',
    name: 'RL (MuJoCo)',
    description: 'PPO/SAC baseline with parallel environments and MJX support',
    icon: '🤖',
    language: 'Python',
    features: ['MuJoCo 3', 'Parallel Envs', 'TensorBoard', 'Checkpointing']
  },
  {
    id: 'rl-pybullet',
    name: 'RL (PyBullet)',
    description: 'PPO baseline with URDF loader and curriculum training',
    icon: '🎮',
    language: 'Python',
    features: ['PyBullet', 'URDF Support', 'Curriculum', 'SB3']
  },
  {
    id: 'slam',
    name: 'SLAM',
    description: 'ORB-SLAM2 baseline with KITTI/TUM dataset loaders',
    icon: '📍',
    language: 'C++',
    features: ['ORB-SLAM2', 'KITTI/TUM', 'Metrics', 'Notebooks']
  },
  {
    id: 'empty',
    name: 'Empty Project',
    description: 'Minimal C++ + Python starter with tests and CI',
    icon: '📄',
    language: 'Mixed',
    features: ['CMake', 'pytest', 'CI/CD', 'Minimal']
  }
];

const ProjectsPage = () => {
  const { token } = useAuth();
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [projectDescription, setProjectDescription] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);

  const { data: projects, isLoading, isError } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: () => fetchProjects(token!)
  });

  const { data: organizations } = useQuery<Organization[]>({
    queryKey: ['organizations'],
    queryFn: () => fetchOrganizations(token!),
    enabled: Boolean(token)
  });

  // Auto-select first organization if available
  useEffect(() => {
    if (organizations && organizations.length > 0 && !selectedOrgId) {
      setSelectedOrgId(organizations[0].id);
    }
  }, [organizations, selectedOrgId]);

  const createProjectMutation = useMutation({
    mutationFn: async (payload: CreateProjectPayload) => {
      // Determine engine based on selected template (not template_id which is a UUID)
      const engine = payload.selectedTemplate === 'rl-pybullet' ? 'pybullet' : 'mujoco';
      console.log('🔍 Creating project with selected template:', payload.selectedTemplate);
      console.log('🔍 Determined engine:', engine);
      
      // Remove selectedTemplate from payload before sending to API
      const { selectedTemplate, ...apiPayload } = payload;
      
      const payloadWithSettings = {
        ...apiPayload,
        settings: { engine }
      };
      
      console.log('🔍 Final payload:', JSON.stringify(payloadWithSettings, null, 2));
      
      const { data } = await authorizedClient(token!).post<Project>('/v1/projects', payloadWithSettings);
      
      console.log('✅ Project created:', data);
      console.log('✅ Project settings:', data.settings);
      
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      setShowModal(false);
      setProjectName('');
      setProjectDescription('');
      setSelectedTemplate(null);
    }
  });

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (projectName.trim() && selectedOrgId) {
      // Generate slug from project name
      const slug = projectName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      
      createProjectMutation.mutate({
        name: projectName,
        description: projectDescription,
        organization_id: selectedOrgId,
        slug: slug,
        template_id: undefined,  // Don't send template_id since we're using settings.engine instead
        selectedTemplate: selectedTemplate  // Pass this for engine determination
      } as CreateProjectPayload);
    } else if (!selectedOrgId) {
      alert('Please select an organization first');
    }
  };

  return (
    <Layout title="Projects">
      <div style={{ marginBottom: '2rem' }}>
        {/* Hero Section */}
        <div style={{
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          borderRadius: '16px',
          padding: '3rem 2rem',
          color: 'white',
          marginBottom: '2rem',
          boxShadow: '0 20px 60px rgba(102, 126, 234, 0.3)'
        }}>
          <h1 style={{ margin: '0 0 0.5rem 0', fontSize: '2.5rem', fontWeight: '700' }}>
            Your Projects
          </h1>
          <p style={{ margin: '0 0 1.5rem 0', fontSize: '1.125rem', opacity: 0.95 }}>
            Build, collaborate, and deploy robotics applications with Python & C++
          </p>
          <button
            onClick={() => setShowModal(true)}
            style={{
              background: 'white',
              color: '#667eea',
              border: 'none',
              borderRadius: '8px',
              padding: '0.75rem 1.5rem',
              fontWeight: '600',
              fontSize: '1rem',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.5rem',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.1)',
              transition: 'transform 0.2s ease, box-shadow 0.2s ease',
              cursor: 'pointer'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 6px 24px rgba(0, 0, 0, 0.15)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.1)';
            }}
          >
            <PlusIcon />
            Create New Project
          </button>
        </div>

        {/* Loading State */}
        {isLoading && (
          <div style={{ textAlign: 'center', padding: '3rem' }}>
            <div style={{
              width: '48px',
              height: '48px',
              border: '4px solid #e2e8f0',
              borderTopColor: '#667eea',
              borderRadius: '50%',
              animation: 'spin 1s linear infinite',
              margin: '0 auto 1rem'
            }} />
            <p style={{ color: '#64748b' }}>Loading your projects...</p>
          </div>
        )}

        {/* Error State */}
        {isError && (
          <div className="card" style={{ 
            border: '2px solid #fecaca', 
            background: '#fef2f2',
            textAlign: 'center',
            padding: '2rem'
          }}>
            <p style={{ color: '#b91c1c', fontWeight: 600, margin: 0 }}>
              ⚠️ Unable to load projects. Please try refreshing the page.
            </p>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !isError && projects && projects.length === 0 && (
          <div className="card" style={{ 
            textAlign: 'center', 
            padding: '4rem 2rem',
            background: 'linear-gradient(to bottom, #ffffff, #f8fafc)'
          }}>
            <div style={{ marginBottom: '1.5rem', opacity: 0.4 }}>
              <FolderIcon />
            </div>
            <h2 style={{ margin: '0 0 0.5rem 0', color: '#1e293b' }}>No projects yet</h2>
            <p style={{ color: '#64748b', margin: '0 0 1.5rem 0', maxWidth: '400px', marginLeft: 'auto', marginRight: 'auto' }}>
              Get started by creating your first robotics project. Choose from templates optimized for SLAM or RL workflows.
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="primary-button"
              style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <PlusIcon />
              Create Your First Project
            </button>
          </div>
        )}

        {/* Projects Grid */}
        {!isLoading && !isError && projects && projects.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: '1.5rem'
          }}>
            {projects.map(project => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                style={{
                  textDecoration: 'none',
                  color: 'inherit'
                }}
              >
                <div
                  className="card"
                  style={{
                    height: '100%',
                    transition: 'all 0.3s ease',
                    cursor: 'pointer',
                    position: 'relative',
                    overflow: 'hidden',
                    border: '1px solid #e2e8f0'
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.transform = 'translateY(-4px)';
                    e.currentTarget.style.boxShadow = '0 12px 32px rgba(15, 23, 42, 0.12)';
                    e.currentTarget.style.borderColor = '#667eea';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = '0 4px 24px rgba(15, 23, 42, 0.06)';
                    e.currentTarget.style.borderColor = '#e2e8f0';
                  }}
                >
                  {/* Gradient accent */}
                  <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: '4px',
                    background: 'linear-gradient(90deg, #667eea 0%, #764ba2 100%)'
                  }} />
                  
                  <div style={{ paddingTop: '0.5rem' }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.75rem',
                      marginBottom: '0.75rem'
                    }}>
                      <div style={{
                        width: '48px',
                        height: '48px',
                        borderRadius: '12px',
                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: 'white',
                        fontSize: '1.5rem',
                        flexShrink: 0
                      }}>
                        {project.template_id === 'slam' ? '📍' : 
                         project.template_id?.startsWith('rl') ? '🤖' : '📁'}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <h3 style={{
                          margin: 0,
                          fontSize: '1.25rem',
                          fontWeight: '600',
                          color: '#1e293b',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}>
                          {project.name}
                        </h3>
                        <p style={{
                          margin: '0.25rem 0 0 0',
                          fontSize: '0.875rem',
                          color: '#64748b'
                        }}>
                          {new Date(project.created_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>

                    {project.description && (
                      <p style={{
                        margin: '0 0 1rem 0',
                        color: '#475569',
                        fontSize: '0.9375rem',
                        lineHeight: '1.5',
                        display: '-webkit-box',
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden'
                      }}>
                        {project.description}
                      </p>
                    )}

                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      paddingTop: '1rem',
                      borderTop: '1px solid #e2e8f0'
                    }}>
                      <div style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '0.25rem',
                        padding: '0.25rem 0.75rem',
                        borderRadius: '6px',
                        background: '#ede9fe',
                        color: '#7c3aed',
                        fontSize: '0.8125rem',
                        fontWeight: 500
                      }}>
                        <CodeIcon />
                        {project.template_id || 'Custom'}
                      </div>
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Create Project Modal */}
      {showModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: '1rem',
          backdropFilter: 'blur(4px)'
        }} onClick={() => setShowModal(false)}>
          <div
            className="card"
            style={{
              maxWidth: '800px',
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              position: 'relative'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '1.5rem',
              paddingBottom: '1rem',
              borderBottom: '2px solid #e2e8f0'
            }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.75rem', color: '#1e293b' }}>
                  Create New Project
                </h2>
                <p style={{ margin: '0.25rem 0 0 0', color: '#64748b' }}>
                  Choose a template and get started in seconds
                </p>
              </div>
              <button
                onClick={() => setShowModal(false)}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  cursor: 'pointer',
                  padding: '0.5rem',
                  borderRadius: '6px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                <CloseIcon />
              </button>
            </div>

            <form onSubmit={handleCreateProject}>
              {/* Project Details */}
              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '0.5rem',
                  fontWeight: 600,
                  color: '#1e293b'
                }}>
                  Project Name *
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="e.g., Robot Navigation SLAM"
                  required
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    fontSize: '1rem',
                    border: '2px solid #e2e8f0',
                    borderRadius: '8px'
                  }}
                />
              </div>

              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '0.5rem',
                  fontWeight: 600,
                  color: '#1e293b'
                }}>
                  Description
                </label>
                <textarea
                  value={projectDescription}
                  onChange={(e) => setProjectDescription(e.target.value)}
                  placeholder="Brief description of your project..."
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '0.75rem',
                    fontSize: '1rem',
                    border: '2px solid #e2e8f0',
                    borderRadius: '8px',
                    resize: 'vertical'
                  }}
                />
              </div>

              {/* Template Selection */}
              <div style={{ marginBottom: '1.5rem' }}>
                <label style={{
                  display: 'block',
                  marginBottom: '0.75rem',
                  fontWeight: 600,
                  color: '#1e293b'
                }}>
                  Choose Template
                </label>
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: '1rem'
                }}>
                  {TEMPLATES.map(template => (
                    <div
                      key={template.id}
                      onClick={() => setSelectedTemplate(template.id)}
                      style={{
                        padding: '1rem',
                        border: `2px solid ${selectedTemplate === template.id ? '#667eea' : '#e2e8f0'}`,
                        borderRadius: '8px',
                        cursor: 'pointer',
                        transition: 'all 0.2s ease',
                        background: selectedTemplate === template.id ? '#f5f3ff' : 'white'
                      }}
                    >
                      <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>
                        {template.icon}
                      </div>
                      <h4 style={{
                        margin: '0 0 0.25rem 0',
                        fontSize: '1rem',
                        color: '#1e293b'
                      }}>
                        {template.name}
                      </h4>
                      <p style={{
                        margin: 0,
                        fontSize: '0.8125rem',
                        color: '#64748b',
                        lineHeight: '1.4'
                      }}>
                        {template.description}
                      </p>
                      <div style={{
                        marginTop: '0.5rem',
                        padding: '0.25rem 0.5rem',
                        background: '#ede9fe',
                        color: '#7c3aed',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: 500,
                        display: 'inline-block'
                      }}>
                        {template.language}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div style={{
                display: 'flex',
                gap: '1rem',
                justifyContent: 'flex-end',
                paddingTop: '1rem',
                borderTop: '2px solid #e2e8f0'
              }}>
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="secondary-button"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="primary-button"
                  disabled={createProjectMutation.isPending}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}
                >
                  {createProjectMutation.isPending ? (
                    <>
                      <div style={{
                        width: '16px',
                        height: '16px',
                        border: '2px solid white',
                        borderTopColor: 'transparent',
                        borderRadius: '50%',
                        animation: 'spin 0.8s linear infinite'
                      }} />
                      Creating...
                    </>
                  ) : (
                    <>
                      <PlusIcon />
                      Create Project
                    </>
                  )}
                </button>
              </div>

              {createProjectMutation.isError && (
                <div style={{
                  marginTop: '1rem',
                  padding: '0.75rem',
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '8px',
                  color: '#b91c1c',
                  fontSize: '0.875rem'
                }}>
                  Failed to create project. Please try again.
                </div>
              )}
            </form>
          </div>
        </div>
      )}

      {/* Add keyframes for spin animation */}
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </Layout>
  );
};

export default ProjectsPage;
