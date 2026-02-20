/**
 * useWebRTC Hook - WebRTC connection management for simulation streaming
 * 
 * Handles:
 * - WebRTC peer connection setup
 * - Signaling server communication
 * - ICE candidate exchange
 * - Video stream rendering
 */

import { useEffect, useRef, useState, useCallback } from 'react';

interface UseWebRTCOptions {
  signalingUrl?: string;
  sessionId: string;
  role?: 'viewer' | 'broadcaster';
  iceServers?: RTCIceServer[];
  onError?: (error: Error) => void;
}

interface WebRTCState {
  isConnected: boolean;
  isConnecting: boolean;
  connectionState: RTCPeerConnectionState;
  error: Error | null;
}

export const useWebRTC = ({
  signalingUrl,
  sessionId,
  role = 'viewer',
  iceServers = [
    { urls: 'stun:stun.l.google.com:19302' },
    { urls: 'stun:stun1.l.google.com:19302' },
  ],
  onError,
}: UseWebRTCOptions) => {
  const [state, setState] = useState<WebRTCState>({
    isConnected: false,
    isConnecting: false,
    connectionState: 'new',
    error: null,
  });

  const videoRef = useRef<HTMLVideoElement>(null);
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const signalingSocketRef = useRef<WebSocket | null>(null);
  const clientIdRef = useRef<string | null>(null);
  const remoteClientIdRef = useRef<string | null>(null);

  /**
   * Send message to signaling server
   */
  const sendSignalingMessage = useCallback((message: any) => {
    const ws = signalingSocketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    } else {
      console.error('❌ Signaling socket not ready');
    }
  }, []);

  /**
   * Create peer connection
   */
  const createPeerConnection = useCallback(() => {
    const pc = new RTCPeerConnection({ iceServers });

    // Handle connection state changes
    pc.onconnectionstatechange = () => {
      console.log('🔄 Connection state:', pc.connectionState);
      setState(prev => ({ ...prev, connectionState: pc.connectionState }));

      if (pc.connectionState === 'connected') {
        setState(prev => ({ ...prev, isConnected: true, isConnecting: false }));
      } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        setState(prev => ({ ...prev, isConnected: false, isConnecting: false }));
      }
    };

    // Handle ICE candidates
    pc.onicecandidate = (event) => {
      if (event.candidate && remoteClientIdRef.current) {
        console.log('🧊 Sending ICE candidate');
        sendSignalingMessage({
          type: 'ice-candidate',
          targetId: remoteClientIdRef.current,
          candidate: event.candidate,
        });
      }
    };

    // Handle incoming media tracks
    pc.ontrack = (event) => {
      console.log('🎥 Received remote track:', event.track.kind);
      if (videoRef.current && event.streams[0]) {
        videoRef.current.srcObject = event.streams[0];
      }
    };

    peerConnectionRef.current = pc;
    return pc;
  }, [iceServers, sendSignalingMessage]);

  /**
   * Handle offer from remote peer
   */
  const handleOffer = useCallback(async (fromId: string, offer: RTCSessionDescriptionInit) => {
    console.log('📨 Received offer from:', fromId);
    remoteClientIdRef.current = fromId;

    const pc = peerConnectionRef.current || createPeerConnection();

    try {
      await pc.setRemoteDescription(new RTCSessionDescription(offer));
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);

      sendSignalingMessage({
        type: 'answer',
        targetId: fromId,
        answer: pc.localDescription,
      });

      console.log('✅ Sent answer');
    } catch (error) {
      console.error('❌ Error handling offer:', error);
      const err = error instanceof Error ? error : new Error('Failed to handle offer');
      setState(prev => ({ ...prev, error: err }));
      onError?.(err);
    }
  }, [createPeerConnection, sendSignalingMessage, onError, role]);

  /**
   * Handle answer from remote peer
   */
  const handleAnswer = useCallback(async (fromId: string, answer: RTCSessionDescriptionInit) => {
    console.log('📨 Received answer from:', fromId);

    const pc = peerConnectionRef.current;
    if (!pc) {
      console.error('❌ No peer connection');
      return;
    }

    try {
      await pc.setRemoteDescription(new RTCSessionDescription(answer));
      console.log('✅ Set remote description');
    } catch (error) {
      console.error('❌ Error handling answer:', error);
      const err = error instanceof Error ? error : new Error('Failed to handle answer');
      setState(prev => ({ ...prev, error: err }));
      onError?.(err);
    }
  }, [onError]);

  /**
   * Handle ICE candidate from remote peer
   */
  const handleIceCandidate = useCallback(async (fromId: string, candidate: RTCIceCandidateInit) => {
    console.log('🧊 Received ICE candidate from:', fromId);

    const pc = peerConnectionRef.current;
    if (!pc) {
      console.error('❌ No peer connection');
      return;
    }

    try {
      await pc.addIceCandidate(new RTCIceCandidate(candidate));
    } catch (error) {
      console.error('❌ Error adding ICE candidate:', error);
    }
  }, []);

  /**
   * Create offer (for broadcaster role)
   */
  const createOffer = useCallback(async (targetId: string) => {
    console.log('📤 Creating offer for:', targetId);
    remoteClientIdRef.current = targetId;

    const pc = peerConnectionRef.current || createPeerConnection();

    try {
      if (role === 'viewer' && pc.getTransceivers().every(t => t.receiver.track?.kind !== 'video')) {
        pc.addTransceiver('video', { direction: 'recvonly' });
      }
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      sendSignalingMessage({
        type: 'offer',
        targetId: targetId,
        offer: pc.localDescription,
      });

      console.log('✅ Sent offer');
    } catch (error) {
      console.error('❌ Error creating offer:', error);
      const err = error instanceof Error ? error : new Error('Failed to create offer');
      setState(prev => ({ ...prev, error: err }));
      onError?.(err);
    }
  }, [createPeerConnection, sendSignalingMessage, onError]);

  /**
   * Connect to signaling server and establish WebRTC
   */
  useEffect(() => {
    if (!signalingUrl) {
      setState({ isConnected: false, isConnecting: false, connectionState: 'new', error: null });
      return;
    }

    setState(prev => ({ ...prev, isConnecting: true }));

    // Connect to signaling server
    const ws = new WebSocket(signalingUrl);
    signalingSocketRef.current = ws;

    ws.onopen = () => {
      console.log('✅ Connected to signaling server');
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      switch (message.type) {
        case 'welcome':
          clientIdRef.current = message.clientId;
          console.log('👋 Welcome, client ID:', message.clientId);

          // Join room
          sendSignalingMessage({
            type: 'join',
            roomId: sessionId,
            role: role,
          });
          break;

        case 'joined':
          console.log('✅ Joined room:', message.roomId);
          console.log('👥 Participants:', message.participants);

          // If viewer and broadcaster exists, initiate connection
          if (role === 'viewer' && message.participants) {
            const broadcaster = message.participants.find((p: any) => p.role === 'broadcaster');
            if (broadcaster) {
              console.log('📞 Found broadcaster, creating offer');
              createOffer(broadcaster.id);
            }
          }
          break;

        case 'peer-joined':
          console.log('👤 Peer joined:', message.peerId, message.role);

          if (role === 'broadcaster' && message.role === 'viewer') {
            console.log('👀 Viewer joined, waiting for offer');
          }
          if (role === 'viewer' && message.role === 'broadcaster') {
            console.log('📞 Broadcaster joined, creating offer');
            createOffer(message.peerId);
          }
          break;

        case 'offer':
          handleOffer(message.fromId, message.offer);
          break;

        case 'answer':
          handleAnswer(message.fromId, message.answer);
          break;

        case 'ice-candidate':
          handleIceCandidate(message.fromId, message.candidate);
          break;

        case 'peer-left':
          console.log('👋 Peer left:', message.peerId);
          // Clean up peer connection if needed
          break;

        case 'error':
          console.error('❌ Signaling error:', message.error);
          const err = new Error(message.error);
          setState(prev => ({ ...prev, error: err, isConnecting: false }));
          onError?.(err);
          break;
      }
    };

    ws.onerror = (error) => {
      console.error('❌ WebSocket error:', error);
      const err = new Error('WebSocket connection failed');
      setState(prev => ({ ...prev, error: err, isConnecting: false }));
      onError?.(err);
    };

    ws.onclose = () => {
      console.log('❌ Disconnected from signaling server');
      setState(prev => ({ ...prev, isConnected: false, isConnecting: false }));
    };

    // Cleanup
    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        sendSignalingMessage({ type: 'leave' });
      }
      ws.close();

      if (peerConnectionRef.current) {
        peerConnectionRef.current.close();
        peerConnectionRef.current = null;
      }
    };
  }, [signalingUrl, sessionId, role, sendSignalingMessage, createOffer, handleOffer, handleAnswer, handleIceCandidate, onError]);

  return {
    videoRef,
    ...state,
  };
};
