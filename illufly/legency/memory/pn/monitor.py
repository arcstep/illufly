import torch
import numpy as np
import matplotlib.pyplot as plt
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
import logging

logger = logging.getLogger(__name__)

class FeatureMonitor:
    """实时特征分析工具"""
    def __init__(self):
        self.feature_bank = []
        
    def log_features(self, features: np.ndarray, label: int):
        """修复特征记录方法"""
        # 确保输入为numpy数组
        if isinstance(features, torch.Tensor):
            features = features.cpu().numpy()
        self.feature_bank.append((features.astype(np.float32), label))
        
    def visualize(self):
        """增强可视化方法"""
        if not self.feature_bank:
            logger.warning("无特征数据可供可视化")
            return
            
        try:
            # 分离特征和标签
            features, labels = zip(*self.feature_bank)
            features_array = np.vstack(features)  # 修复元组转换问题
            
            # 添加PCA预处理
            from sklearn.decomposition import PCA
            pca = PCA(n_components=50)
            reduced_pca = pca.fit_transform(features_array)
            
            # 执行t-SNE
            from sklearn.manifold import TSNE
            tsne = TSNE(n_components=2, perplexity=min(30, len(features_array)-1))
            reduced = tsne.fit_transform(reduced_pca)
            
            # 可视化
            import matplotlib.pyplot as plt
            plt.figure(figsize=(10, 8))
            scatter = plt.scatter(reduced[:,0], reduced[:,1], c=labels, alpha=0.6, cmap='viridis')
            plt.colorbar(scatter)
            plt.title("Enhanced Feature Space (t-SNE)")
            plt.savefig("./feature_visualization.png")
            plt.close()
        except Exception as e:
            logger.error(f"特征可视化失败: {str(e)}")

    def calculate_separability(self) -> float:
        """新增特征可分性计算"""
        from sklearn.svm import LinearSVC
        from sklearn.model_selection import cross_val_score
        
        if not self.feature_bank:
            return 0.0
            
        features, labels = zip(*self.feature_bank)
        try:
            clf = LinearSVC(max_iter=10000)
            scores = cross_val_score(clf, features, labels, cv=3)
            return float(np.mean(scores))
        except Exception as e:
            logger.error(f"可分性计算失败: {str(e)}")
            return 0.0

    def enhanced_metrics(self):
        """新增监控指标"""
        return {
            'batch_loss_std': np.std(self.loss_history[-50:]),
            'grad_norm': np.mean(self.grad_norms),
            'lr_trend': self.learning_rates[-100:]
        }
